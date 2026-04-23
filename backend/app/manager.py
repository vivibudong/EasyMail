from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import queue
import re
import threading
import time
from dataclasses import asdict
from typing import Optional

from .imap_logic import (
    fetch_mail_body,
    fetch_mails_once,
    format_shanghai_time,
    get_graph_access_token,
    get_oauth_access_token,
    parse_text_to_accounts,
    probe_account_login,
)
from .models import (
    AppSettings,
    BodyTask,
    DEFAULT_IMPORT_DELIMITERS,
    GroupDefinition,
    MailAccount,
    MailItem,
    TagDefinition,
    account_to_dict,
    normalize_import_delimiters,
    settings_to_dict,
)
from .storage import SqliteStorage


class MailManager:
    def __init__(self, storage: SqliteStorage) -> None:
        self.storage = storage
        self.lock = threading.RLock()

        self.accounts: list[MailAccount] = self.storage.load_accounts()
        self.local_read_keys: set[str] = self.storage.load_read_state()
        self.settings: AppSettings = self.storage.load_settings()

        self.all_mails: list[MailItem] = []
        self.mail_items: dict[str, MailItem] = {}
        self.body_tasks: dict[str, BodyTask] = {}

        self.login_q: queue.Queue[MailAccount] = queue.Queue()
        self.receive_q: queue.Queue[MailAccount] = queue.Queue()
        self.body_q: queue.Queue[tuple[MailAccount, MailItem]] = queue.Queue()

        self.queued_login: set[str] = set()
        self.queued_receive: set[str] = set()
        self.queued_body: set[str] = set()

        self.login_total = 0
        self.login_done = 0
        self.receive_total = 0
        self.receive_done = 0
        self.login_busy_email = ""
        self.receive_busy_email = ""

        self.token_refresh_running = False
        self.backup_running = False
        self.scheduler_stop = threading.Event()
        task_state = self.storage.load_task_state("scheduler")
        self.last_auto_receive_run_at = float(task_state.get("last_auto_receive_run_at", 0.0) or 0.0)
        self.last_token_refresh_run_at = float(task_state.get("last_token_refresh_run_at", 0.0) or 0.0)
        self.last_backup_run_at = float(task_state.get("last_backup_run_at", 0.0) or 0.0)

        self.settings.custom_groups = self._sort_groups(self.settings.custom_groups)
        self.settings.custom_tags = self._sort_tags(self.settings.custom_tags)
        self.settings.import_delimiters = normalize_import_delimiters(self.settings.import_delimiters)

        repaired_accounts = self._repair_legacy_imported_accounts()
        for account in self.accounts:
            if not account.group_name:
                account.group_name = "未分组"
            account.mails = self.storage.load_mail_cache(account, self.local_read_keys)
            if account.mails and account.status == "待登录":
                account.status = "已缓存"
        if repaired_accounts:
            self._save_accounts_state()
            self.log_event(
                "info",
                "account",
                "repair_import",
                "batch",
                "修复旧导入账号字段",
                {"count": repaired_accounts},
            )
        self.rebuild_mail_pool()
        self._start_workers()
        if self.accounts and self.settings.startup_auto_login:
            self.start_relogin_batch(self.accounts.copy())

    def _start_workers(self) -> None:
        threading.Thread(target=self.login_worker, daemon=True).start()
        threading.Thread(target=self.receive_worker, daemon=True).start()
        threading.Thread(target=self.body_worker, daemon=True).start()
        threading.Thread(target=self.scheduler_worker, daemon=True).start()

    def _persist_scheduler_state(self) -> None:
        self.storage.save_task_state(
            "scheduler",
            {
                "last_auto_receive_run_at": self.last_auto_receive_run_at,
                "last_token_refresh_run_at": self.last_token_refresh_run_at,
                "last_backup_run_at": self.last_backup_run_at,
            },
        )

    def log_event(
        self,
        level: str,
        category: str,
        action: str,
        subject: str,
        message: str,
        detail: dict | str | None = None,
    ) -> None:
        try:
            self.storage.append_log(level, category, action, subject, message, detail)
        except Exception:
            pass

    def _normalize_group_name(self, group_name: str) -> str:
        name = group_name.strip() or "未分组"
        if name in {"全部", "星标", "标签"}:
            raise ValueError("该分组名称为保留名称")
        return name

    def _normalize_tag_name(self, tag_name: str) -> str:
        name = tag_name.strip()
        if not name:
            raise ValueError("标签名称不能为空")
        if name in {"全部", "星标", "分组", "标签", "未分组"}:
            raise ValueError("该标签名称为保留名称")
        return name

    def _sort_groups(self, groups: list[GroupDefinition]) -> list[GroupDefinition]:
        return sorted(groups, key=lambda item: (-item.priority, item.name.lower()))

    def _sort_tags(self, tags: list[TagDefinition]) -> list[TagDefinition]:
        return sorted(tags, key=lambda item: (-item.priority, item.name.lower()))

    def summarize_error_text(self, raw_text: str) -> str:
        text = raw_text.strip()
        if not text:
            return ""
        parts: list[str] = []
        if "NoPrimarySmtpAddress" in text or "not connected" in text:
            parts.append("账号已认证，但当前邮箱不可连接")
        if "BasicAuthBlocked" in text:
            parts.append("基础认证已被微软禁用，请改用 OAuth2")
        if "invalid_grant" in text.lower() or "bad request" in text.lower():
            parts.append("刷新令牌可能已失效，需要重新授权")
        if "AADSTS70000" in text and "scope" in text.lower():
            parts.append("当前令牌未授予所请求的权限范围")
        if "AADSTS70011" in text:
            parts.append("请求的权限范围参数无效")
        if "缺少第4段令牌" in text:
            parts.append("缺少刷新令牌")
        if "缺少第3段ClientID" in text:
            parts.append("缺少 Client ID")
        if "AUTHENTICATE failed" in text and not parts:
            parts.append("IMAP 身份认证失败")
        if not parts:
            compact = re.sub(r"\s+", " ", text)
            return compact[:120] + ("..." if len(compact) > 120 else "")
        seen: list[str] = []
        for item in parts:
            if item not in seen:
                seen.append(item)
        return "；".join(seen)

    def _folder_display_name(self, folder_name: str) -> str:
        lowered = folder_name.lower()
        if lowered in {"inbox", "收件箱"}:
            return "收件箱"
        if lowered in {"junk", "junk email", "junk e-mail", "junkemail", "spam", "垃圾邮件"}:
            return "垃圾邮件"
        if lowered in {"deleted items", "deleteditems", "trash", "已删除"}:
            return "已删除"
        return folder_name

    def _save_accounts_state(self) -> None:
        self.storage.save_accounts(self.accounts)

    def _repair_legacy_imported_accounts(self) -> int:
        repaired = 0
        for index, account in enumerate(self.accounts):
            if account.password or account.auth_code_or_client_id or account.token:
                continue
            if "@" not in account.email or not any(token in account.email for token in ("||", "---", "|", ",", ";", "\t")):
                continue
            parsed = parse_text_to_accounts(
                account.email,
                import_delimiters=self.settings.import_delimiters or DEFAULT_IMPORT_DELIMITERS.copy(),
                comment_prefix=self.settings.txt_comment_prefix,
                skip_first_line=False,
            )
            if not parsed:
                continue
            repaired_account = parsed[0]
            if repaired_account.email == account.email:
                continue
            duplicate = next(
                (
                    item
                    for item_index, item in enumerate(self.accounts)
                    if item_index != index and item.email.lower() == repaired_account.email.lower()
                ),
                None,
            )
            if duplicate is not None:
                continue
            repaired_account.group_name = account.group_name or "未分组"
            repaired_account.flag_color = account.flag_color
            repaired_account.tags = account.tags.copy()
            repaired_account.mails = account.mails
            repaired_account.status = "待登录"
            repaired_account.last_check = account.last_check
            repaired_account.unseen_count = account.unseen_count
            repaired_account.last_error = account.last_error
            repaired_account.auth_method = account.auth_method
            repaired_account.cached_access_token = ""
            repaired_account.cached_access_expire_at = 0.0
            repaired_account.cached_graph_access_token = ""
            repaired_account.cached_graph_access_expire_at = 0.0
            self.accounts[index] = repaired_account
            repaired += 1
        return repaired

    def find_account(self, email_addr: str) -> Optional[MailAccount]:
        for account in self.accounts:
            if account.email == email_addr:
                return account
        return None

    def rebuild_mail_pool(self) -> None:
        self.all_mails.clear()
        self.mail_items.clear()
        seen: set[str] = set()
        for account in self.accounts:
            for item in account.mails:
                item.folder = self._folder_display_name(item.folder)
                if item.local_key in seen:
                    continue
                seen.add(item.local_key)
                self.all_mails.append(item)
                self.mail_items[item.local_key] = item
        self.all_mails.sort(key=lambda item: item.date_value, reverse=True)

    def reset_login_progress(self) -> None:
        self.login_total = 0
        self.login_done = 0
        self.login_busy_email = ""

    def reset_receive_progress(self) -> None:
        self.receive_total = 0
        self.receive_done = 0
        self.receive_busy_email = ""

    def enqueue_login(self, account: MailAccount) -> None:
        if account.email in self.queued_login:
            return
        self.queued_login.add(account.email)
        self.login_total += 1
        self.login_q.put(account)

    def enqueue_receive(self, account: MailAccount) -> None:
        if account.email in self.queued_receive:
            return
        self.queued_receive.add(account.email)
        self.receive_total += 1
        self.receive_q.put(account)

    def enqueue_body(self, account: MailAccount, item: MailItem) -> BodyTask:
        if item.local_key in self.queued_body:
            return self.body_tasks.setdefault(
                item.local_key, BodyTask(state="queued", status="等待下载正文")
            )
        self.queued_body.add(item.local_key)
        task = BodyTask(state="queued", status="等待下载正文")
        self.body_tasks[item.local_key] = task
        self.body_q.put((account, item))
        return task

    def _queue_progress(self) -> dict:
        total = self.login_total + self.receive_total
        done = self.login_done + self.receive_done
        percent = int((done / total) * 100) if total else 0
        return {
            "login_total": self.login_total,
            "login_done": self.login_done,
            "receive_total": self.receive_total,
            "receive_done": self.receive_done,
            "login_busy_email": self.login_busy_email,
            "receive_busy_email": self.receive_busy_email,
            "pending_login_emails": sorted(
                email for email in self.queued_login if email != self.login_busy_email
            ),
            "pending_receive_emails": sorted(
                email for email in self.queued_receive if email != self.receive_busy_email
            ),
            "pending_body_keys": sorted(self.queued_body),
            "percent": percent,
        }

    def overview(self) -> dict:
        return {
            "total_accounts": len(self.accounts),
            "success_accounts": sum(1 for item in self.accounts if item.status == "登录成功"),
            "failed_accounts": sum(
                1 for item in self.accounts if item.status in {"登录失败", "收信失败"}
            ),
            "processing_accounts": sum(
                1 for item in self.accounts if item.status in {"登录中", "收信中"}
            ),
            "cached_mails": len(self.all_mails),
            "unread_mails": sum(1 for item in self.all_mails if item.is_unread),
            "queue": self._queue_progress(),
        }

    def serialize_account(self, account: MailAccount, index: int) -> dict:
        return {
            "index": index,
            "email": account.email,
            "group_name": account.group_name or "未分组",
            "tags": account.tags,
            "status": account.status,
            "last_check": account.last_check,
            "unseen_count": account.unseen_count,
            "last_error": account.last_error,
            "last_error_summary": self.summarize_error_text(account.last_error),
            "auth_method": account.auth_method,
            "flag_color": account.flag_color,
            "mail_count": len(account.mails),
        }

    def serialize_mail(self, item: MailItem) -> dict:
        return {
            "account_email": item.account_email,
            "folder": self._folder_display_name(item.folder),
            "local_key": item.local_key,
            "source": item.source,
            "subject": item.subject,
            "from_text": item.from_text,
            "date_text": item.date_text,
            "date_value": item.date_value.isoformat(),
            "is_unread": item.is_unread,
            "is_starred": item.is_starred,
            "has_body": bool(item.body_text),
            "body_text": item.body_text,
        }

    def dashboard_state(self) -> dict:
        with self.lock:
            return {
                "overview": self.overview(),
                "accounts": [
                    self.serialize_account(account, idx)
                    for idx, account in enumerate(self.accounts, start=1)
                ],
                "mails": [self.serialize_mail(item) for item in self.all_mails],
                "settings": settings_to_dict(self.settings),
            }

    def start_receive_batch(self, targets: list[Optional[MailAccount]]) -> int:
        with self.lock:
            items = [item for item in targets if item]
            self.reset_receive_progress()
            for account in items:
                self.enqueue_receive(account)
            return len(items)

    def start_relogin_batch(self, targets: list[Optional[MailAccount]]) -> int:
        with self.lock:
            items = [item for item in targets if item]
            self.reset_login_progress()
            for account in items:
                self.enqueue_login(account)
            return len(items)

    def delete_accounts(self, emails: set[str]) -> int:
        with self.lock:
            if not emails:
                return 0
            for email_addr in emails:
                self.storage.remove_mail_cache(email_addr)
                prefix = f"{email_addr}|"
                self.local_read_keys = {
                    item for item in self.local_read_keys if not item.startswith(prefix)
                }
                self.body_tasks = {
                    key: value
                    for key, value in self.body_tasks.items()
                    if not key.startswith(prefix)
                }
            self.accounts = [item for item in self.accounts if item.email not in emails]
            self.storage.save_read_state(self.local_read_keys)
            self._save_accounts_state()
            self.rebuild_mail_pool()
            return len(emails)

    def set_flag(self, email_addr: str, color: str) -> None:
        with self.lock:
            account = self.find_account(email_addr)
            if not account:
                raise ValueError("邮箱不存在")
            account.flag_color = color
            self._save_accounts_state()

    def create_group(self, group_name: str, color: str = "#D6EAF8", priority: int = 100) -> list[dict]:
        with self.lock:
            normalized = self._normalize_group_name(group_name)
            if normalized == "未分组":
                return settings_to_dict(self.settings)["custom_groups"]
            if any(item.name == normalized for item in self.settings.custom_groups):
                raise ValueError("分组已存在")
            self.settings.custom_groups.append(
                GroupDefinition(
                    name=normalized,
                    color=color.strip() or "#D6EAF8",
                    priority=max(1, min(999, int(priority or 100))),
                )
            )
            self.settings.custom_groups = self._sort_groups(self.settings.custom_groups)
            self.storage.save_settings(self.settings)
            self.log_event("info", "group", "create", normalized, "创建分组", {"color": color, "priority": priority})
            return settings_to_dict(self.settings)["custom_groups"]

    def update_group(self, original_name: str, new_name: str, color: str, priority: int) -> list[dict]:
        with self.lock:
            if original_name == "未分组":
                raise ValueError("未分组不能直接修改")
            target = next((item for item in self.settings.custom_groups if item.name == original_name), None)
            if not target:
                raise ValueError("分组不存在")
            normalized = self._normalize_group_name(new_name)
            if normalized != original_name and any(item.name == normalized for item in self.settings.custom_groups):
                raise ValueError("目标分组已存在")
            for account in self.accounts:
                if account.group_name == original_name:
                    account.group_name = normalized
            target.name = normalized
            target.color = color.strip() or "#D6EAF8"
            target.priority = max(1, min(999, int(priority or 100)))
            self.settings.custom_groups = self._sort_groups(self.settings.custom_groups)
            self._save_accounts_state()
            self.storage.save_settings(self.settings)
            self.log_event("info", "group", "update", normalized, "更新分组", {"original_name": original_name, "color": color, "priority": priority})
            return settings_to_dict(self.settings)["custom_groups"]

    def delete_group(self, group_name: str) -> list[dict]:
        with self.lock:
            if group_name == "未分组":
                raise ValueError("未分组不能删除")
            original_count = len(self.settings.custom_groups)
            self.settings.custom_groups = [
                item for item in self.settings.custom_groups if item.name != group_name
            ]
            if len(self.settings.custom_groups) == original_count:
                raise ValueError("分组不存在")
            for account in self.accounts:
                if account.group_name == group_name:
                    account.group_name = "未分组"
            self.settings.custom_groups = self._sort_groups(self.settings.custom_groups)
            self._save_accounts_state()
            self.storage.save_settings(self.settings)
            self.log_event("warn", "group", "delete", group_name, "删除分组", {"moved_to": "未分组"})
            return settings_to_dict(self.settings)["custom_groups"]

    def assign_group(self, email_addr: str, group_name: str) -> None:
        with self.lock:
            account = self.find_account(email_addr)
            if not account:
                raise ValueError("邮箱不存在")
            normalized = self._normalize_group_name(group_name)
            if normalized != "未分组" and not any(
                item.name == normalized for item in self.settings.custom_groups
            ):
                raise ValueError("分组不存在，请先创建")
            account.group_name = normalized
            self._save_accounts_state()
            self.log_event("info", "account", "assign_group", email_addr, "修改邮箱分组", {"group_name": normalized})

    def create_tag(self, tag_name: str, color: str = "#BFDBFE", priority: int = 100) -> list[dict]:
        with self.lock:
            normalized = self._normalize_tag_name(tag_name)
            if any(item.name == normalized for item in self.settings.custom_tags):
                raise ValueError("标签已存在")
            self.settings.custom_tags.append(
                TagDefinition(
                    name=normalized,
                    color=color.strip() or "#BFDBFE",
                    priority=max(1, min(999, int(priority or 100))),
                )
            )
            self.settings.custom_tags = self._sort_tags(self.settings.custom_tags)
            self.storage.save_settings(self.settings)
            self.log_event("info", "tag", "create", normalized, "创建标签", {"color": color, "priority": priority})
            return settings_to_dict(self.settings)["custom_tags"]

    def update_tag(self, original_name: str, new_name: str, color: str, priority: int) -> list[dict]:
        with self.lock:
            target = next((item for item in self.settings.custom_tags if item.name == original_name), None)
            if not target:
                raise ValueError("标签不存在")
            normalized = self._normalize_tag_name(new_name)
            if normalized != original_name and any(item.name == normalized for item in self.settings.custom_tags):
                raise ValueError("目标标签已存在")
            for account in self.accounts:
                account.tags = [normalized if item == original_name else item for item in account.tags]
            target.name = normalized
            target.color = color.strip() or "#BFDBFE"
            target.priority = max(1, min(999, int(priority or 100)))
            self.settings.custom_tags = self._sort_tags(self.settings.custom_tags)
            self._save_accounts_state()
            self.storage.save_settings(self.settings)
            self.log_event("info", "tag", "update", normalized, "更新标签", {"original_name": original_name, "color": color, "priority": priority})
            return settings_to_dict(self.settings)["custom_tags"]

    def delete_tag(self, tag_name: str) -> list[dict]:
        with self.lock:
            original_count = len(self.settings.custom_tags)
            self.settings.custom_tags = [
                item for item in self.settings.custom_tags if item.name != tag_name
            ]
            if len(self.settings.custom_tags) == original_count:
                raise ValueError("标签不存在")
            for account in self.accounts:
                account.tags = [item for item in account.tags if item != tag_name]
            self.settings.custom_tags = self._sort_tags(self.settings.custom_tags)
            self._save_accounts_state()
            self.storage.save_settings(self.settings)
            self.log_event("warn", "tag", "delete", tag_name, "删除标签")
            return settings_to_dict(self.settings)["custom_tags"]

    def set_account_tags(self, email_addr: str, tags: list[str]) -> list[str]:
        with self.lock:
            account = self.find_account(email_addr)
            if not account:
                raise ValueError("邮箱不存在")
            valid_names = {item.name for item in self.settings.custom_tags}
            cleaned: list[str] = []
            for item in tags:
                name = str(item).strip()
                if not name:
                    continue
                if name not in valid_names:
                    raise ValueError(f"标签不存在: {name}")
                if name not in cleaned:
                    cleaned.append(name)
            account.tags = cleaned
            self._save_accounts_state()
            self.log_event("info", "account", "set_tags", email_addr, "设置邮箱标签", {"tags": cleaned})
            return account.tags

    def toggle_mail_star(self, local_key: str, is_starred: Optional[bool] = None) -> bool:
        with self.lock:
            item = self.mail_items.get(local_key)
            if not item:
                raise ValueError("邮件不存在")
            item.is_starred = (not item.is_starred) if is_starred is None else bool(is_starred)
            account = self.find_account(item.account_email)
            if account:
                self.storage.save_mail_cache(account)
            self.log_event("info", "mail", "star", item.local_key, "更新邮件星标", {"is_starred": item.is_starred})
            return item.is_starred

    def get_account_detail(self, email_addr: str) -> dict:
        with self.lock:
            account = self.find_account(email_addr)
            if not account:
                raise ValueError("邮箱不存在")
            return {
                "email": account.email,
                "password": account.password,
                "auth_code_or_client_id": account.auth_code_or_client_id,
                "token": account.token,
                "imap_host": account.imap_host,
                "imap_port": account.imap_port,
                "group_name": account.group_name,
                "flag_color": account.flag_color,
                "tags": account.tags,
            }

    def update_account(self, original_email: str, payload: dict) -> dict:
        with self.lock:
            account = self.find_account(original_email)
            if not account:
                raise ValueError("邮箱不存在")
            new_email = str(payload.get("email", account.email)).strip()
            if "@" not in new_email:
                raise ValueError("邮箱格式无效")
            if new_email != original_email and self.find_account(new_email):
                raise ValueError("该邮箱已存在")
            account.email = new_email
            account.password = str(payload.get("password", account.password))
            account.auth_code_or_client_id = str(
                payload.get("auth_code_or_client_id", account.auth_code_or_client_id)
            )
            account.token = str(payload.get("token", account.token))
            account.imap_host = str(payload.get("imap_host", account.imap_host))
            account.imap_port = int(payload.get("imap_port", account.imap_port) or account.imap_port)
            account.group_name = self._normalize_group_name(
                str(payload.get("group_name", account.group_name))
            )
            account.flag_color = str(payload.get("flag_color", account.flag_color))
            valid_names = {item.name for item in self.settings.custom_tags}
            tags_payload = payload.get("tags", account.tags)
            cleaned_tags: list[str] = []
            if not isinstance(tags_payload, list):
                raise ValueError("标签格式无效")
            for item in tags_payload:
                name = str(item).strip()
                if not name:
                    continue
                if name not in valid_names:
                    raise ValueError(f"标签不存在: {name}")
                if name not in cleaned_tags:
                    cleaned_tags.append(name)
            account.tags = cleaned_tags
            account.status = "待登录"
            account.last_error = ""
            account.cached_access_token = ""
            account.cached_access_expire_at = 0.0
            account.cached_graph_access_token = ""
            account.cached_graph_access_expire_at = 0.0
            self._save_accounts_state()
            self.rebuild_mail_pool()
            self.log_event("info", "account", "update", new_email, "编辑账号", {"original_email": original_email})
            return self.serialize_account(account, self.accounts.index(account) + 1)

    def _decode_text_content(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="ignore")

    def import_accounts(self, file_bytes: bytes) -> dict:
        with self.lock:
            content = self._decode_text_content(file_bytes)
            new_items = parse_text_to_accounts(
                content,
                import_delimiters=self.settings.import_delimiters,
                comment_prefix=self.settings.txt_comment_prefix,
                skip_first_line=self.settings.txt_skip_first_line,
            )
            if not new_items:
                raise ValueError("未识别到有效账号行，请检查分隔符或文本格式")

            old_map = {item.email.lower(): item for item in self.accounts}
            imported_seen: set[str] = set()
            dedup: list[MailAccount] = []
            for item in reversed(new_items):
                key = item.email.lower()
                if key not in imported_seen:
                    imported_seen.add(key)
                    dedup.append(item)
            dedup.reverse()

            old_indices = {item.email.lower(): index for index, item in enumerate(self.accounts)}
            merged = self.accounts.copy()
            need_login: list[MailAccount] = []
            for item in dedup:
                key = item.email.lower()
                old = old_map.get(key)
                if old:
                    same = (
                        old.password == item.password
                        and old.auth_code_or_client_id == item.auth_code_or_client_id
                        and old.token == item.token
                        and old.imap_host == item.imap_host
                        and old.imap_port == item.imap_port
                    )
                    if same:
                        if old.status != "登录成功":
                            need_login.append(old)
                        continue
                    item.group_name = old.group_name
                    item.flag_color = old.flag_color
                    item.tags = old.tags
                    item.mails = old.mails
                    merged[old_indices[key]] = item
                    need_login.append(item)
                    continue
                merged.append(item)
                need_login.append(item)

            self.accounts = merged
            self._save_accounts_state()
            self.rebuild_mail_pool()
            self.reset_login_progress()
            self.reset_receive_progress()
            for account in need_login:
                self.enqueue_login(account)
            self.log_event("info", "account", "import", "batch", "批量导入邮箱", {"imported": len(new_items), "changed": len(need_login)})
            return {"imported": len(new_items), "changed": len(need_login)}

    def update_settings(self, payload: dict) -> dict:
        with self.lock:
            self.settings.auto_receive_interval = int(
                payload.get("auto_receive_interval", self.settings.auto_receive_interval) or 120
            )
            self.settings.import_delimiters = normalize_import_delimiters(
                payload.get("import_delimiters", self.settings.import_delimiters)
            )
            self.settings.txt_comment_prefix = str(
                payload.get("txt_comment_prefix", self.settings.txt_comment_prefix)
            )
            self.settings.txt_skip_first_line = bool(
                payload.get("txt_skip_first_line", self.settings.txt_skip_first_line)
            )
            self.settings.startup_auto_login = bool(
                payload.get("startup_auto_login", self.settings.startup_auto_login)
            )
            self.settings.mail_list_limit = int(
                payload.get("mail_list_limit", self.settings.mail_list_limit) or 0
            )
            self.settings.mark_read_on_open = bool(
                payload.get("mark_read_on_open", self.settings.mark_read_on_open)
            )
            self.settings.auto_receive_enabled = bool(
                payload.get("auto_receive_enabled", self.settings.auto_receive_enabled)
            )
            self.settings.auto_receive_interval_minutes = int(
                payload.get(
                    "auto_receive_interval_minutes",
                    self.settings.auto_receive_interval_minutes,
                )
                or 15
            )
            self.settings.token_refresh_enabled = bool(
                payload.get("token_refresh_enabled", self.settings.token_refresh_enabled)
            )
            self.settings.token_refresh_interval_minutes = int(
                payload.get(
                    "token_refresh_interval_minutes",
                    self.settings.token_refresh_interval_minutes,
                )
                or 360
            )
            self.settings.backup_enabled = bool(
                payload.get("backup_enabled", self.settings.backup_enabled)
            )
            self.settings.backup_interval_minutes = int(
                payload.get("backup_interval_minutes", self.settings.backup_interval_minutes) or 1440
            )
            self.settings.backup_directory = str(
                payload.get("backup_directory", self.settings.backup_directory) or "backups"
            )
            self.settings.backup_keep_count = int(
                payload.get("backup_keep_count", self.settings.backup_keep_count) or 10
            )
            self.settings.oauth_client_id = str(
                payload.get("oauth_client_id", self.settings.oauth_client_id) or ""
            ).strip()
            self.settings.oauth_redirect_uri = str(
                payload.get("oauth_redirect_uri", self.settings.oauth_redirect_uri)
                or "http://localhost:8765/callback"
            ).strip()

            groups_raw = payload.get("custom_groups", settings_to_dict(self.settings)["custom_groups"])
            next_groups: list[GroupDefinition] = []
            for item in groups_raw:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_group_name(str(item.get("name", "")))
                if normalized == "未分组" or any(group.name == normalized for group in next_groups):
                    continue
                next_groups.append(
                    GroupDefinition(
                        name=normalized,
                        color=str(item.get("color", "#D6EAF8") or "#D6EAF8"),
                        priority=max(1, min(999, int(item.get("priority", 100) or 100))),
                    )
                )
            self.settings.custom_groups = self._sort_groups(next_groups)

            tags_raw = payload.get("custom_tags", settings_to_dict(self.settings)["custom_tags"])
            next_tags: list[TagDefinition] = []
            for item in tags_raw:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_tag_name(str(item.get("name", "")))
                if any(tag.name == normalized for tag in next_tags):
                    continue
                next_tags.append(
                    TagDefinition(
                        name=normalized,
                        color=str(item.get("color", "#BFDBFE") or "#BFDBFE"),
                        priority=max(1, min(999, int(item.get("priority", 100) or 100))),
                    )
                )
            self.settings.custom_tags = self._sort_tags(next_tags)
            self.storage.save_settings(self.settings)
            self.log_event("info", "settings", "update", "app_settings", "更新系统设置")
            return settings_to_dict(self.settings)

    def open_mail(self, local_key: str) -> dict:
        with self.lock:
            item = self.mail_items.get(local_key)
            if not item:
                raise ValueError("邮件不存在")
            if self.settings.mark_read_on_open and item.is_unread:
                item.is_unread = False
                self.local_read_keys.add(item.local_key)
                account = self.find_account(item.account_email)
                if account:
                    account.unseen_count = max(0, account.unseen_count - 1)
                    self.storage.save_mail_cache(account)
                self.storage.save_read_state(self.local_read_keys)
            body_task = self.body_tasks.get(local_key)
            if item.body_text:
                size = len(item.body_text.encode("utf-8", errors="ignore"))
                body_task = self.body_tasks[local_key] = BodyTask(
                    state="done",
                    downloaded=size,
                    total=size,
                    status="正文已缓存",
                    size=size,
                )
            else:
                account = self.find_account(item.account_email)
                if account:
                    body_task = self.enqueue_body(account, item)
            self.log_event("info", "mail", "open", local_key, "打开邮件", {"source": item.source, "folder": item.folder})
            return {"mail": self.serialize_mail(item), "body_task": asdict(body_task or BodyTask())}

    def get_body_status(self, local_key: str) -> dict:
        with self.lock:
            item = self.mail_items.get(local_key)
            if not item:
                raise ValueError("邮件不存在")
            task = self.body_tasks.get(local_key, BodyTask())
            return {"mail": self.serialize_mail(item), "body_task": asdict(task)}

    def refresh_all_tokens(self, trigger_source: str = "manual") -> dict:
        with self.lock:
            if self.token_refresh_running:
                raise ValueError("Token 刷新任务正在执行")
            self.token_refresh_running = True
            accounts = [item for item in self.accounts if item.token and item.auth_code_or_client_id]
        self.log_event("info", "token_refresh", "start", trigger_source, "开始刷新 Token", {"count": len(accounts)})
        try:
            results: list[dict] = []
            success_count = 0
            failed_count = 0
            for account in accounts:
                imap_token, imap_message = get_oauth_access_token(account)
                graph_token, graph_message = get_graph_access_token(account)
                ok = bool(imap_token or graph_token)
                if ok:
                    success_count += 1
                else:
                    failed_count += 1
                    self.log_event("error", "token_refresh", "account_failed", account.email, "Token 刷新失败", {"imap": imap_message, "graph": graph_message})
                results.append(
                    {
                        "email": account.email,
                        "success": ok,
                        "imap": imap_message,
                        "graph": graph_message,
                    }
                )
            self._save_accounts_state()
            self.last_token_refresh_run_at = time.time()
            self._persist_scheduler_state()
            summary = {
                "total": len(accounts),
                "success_count": success_count,
                "failed_count": failed_count,
                "results": results,
            }
            self.storage.append_refresh_history(trigger_source, summary)
            self.log_event("info", "token_refresh", "complete", trigger_source, "Token 刷新完成", summary)
            return summary
        finally:
            with self.lock:
                self.token_refresh_running = False

    def get_refresh_history(self, limit: int = 20) -> list[dict]:
        return self.storage.load_refresh_history(limit)

    def export_accounts_text(
        self,
        emails: Optional[list[str]] = None,
        group_name: Optional[str] = None,
    ) -> tuple[str, str]:
        with self.lock:
            accounts = self.accounts
            if emails:
                email_set = set(emails)
                accounts = [account for account in accounts if account.email in email_set]
            elif group_name and group_name not in {"__all__", ""}:
                accounts = [
                    account
                    for account in accounts
                    if (account.group_name or "未分组") == group_name
                ]
            lines = [
                f"{account.email}---{account.password}---{account.auth_code_or_client_id}---{account.token}"
                for account in accounts
            ]
        file_name = f"easymail-export-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        return ("\n".join(lines), file_name)

    def backup_accounts_now(self, trigger_source: str = "manual") -> dict:
        with self.lock:
            if self.backup_running:
                raise ValueError("备份任务正在执行")
            self.backup_running = True
            payload = [account_to_dict(account) for account in self.accounts]
            directory_setting = self.settings.backup_directory.strip() or "backups"
            keep_count = max(1, self.settings.backup_keep_count)
        try:
            backup_dir = Path(directory_setting)
            if not backup_dir.is_absolute():
                backup_dir = self.storage.base_dir / backup_dir
            backup_dir.mkdir(parents=True, exist_ok=True)
            file_path = backup_dir / f"accounts-backup-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            backup_files = sorted(backup_dir.glob("accounts-backup-*.json"), reverse=True)
            for old_file in backup_files[keep_count:]:
                old_file.unlink(missing_ok=True)
            self.last_backup_run_at = time.time()
            self._persist_scheduler_state()
            self.log_event("info", "backup", "complete", trigger_source, "账号备份完成", {"path": str(file_path), "retained": min(len(backup_files), keep_count)})
            return {
                "path": str(file_path),
                "retained": min(len(backup_files), keep_count),
                "trigger_source": trigger_source,
            }
        finally:
            with self.lock:
                self.backup_running = False

    def scheduler_worker(self) -> None:
        while not self.scheduler_stop.is_set():
            try:
                now = time.time()
                with self.lock:
                    settings = self.settings
                    accounts = self.accounts.copy()
                if (
                    settings.token_refresh_enabled
                    and settings.token_refresh_interval_minutes > 0
                    and now - self.last_token_refresh_run_at >= settings.token_refresh_interval_minutes * 60
                ):
                    self.refresh_all_tokens(trigger_source="scheduled")
                if (
                    settings.auto_receive_enabled
                    and settings.auto_receive_interval_minutes > 0
                    and now - self.last_auto_receive_run_at >= settings.auto_receive_interval_minutes * 60
                ):
                    self.start_receive_batch(accounts)
                    self.last_auto_receive_run_at = now
                    self._persist_scheduler_state()
                    self.log_event("info", "scheduler", "auto_receive", "scheduled", "触发定时收件", {"accounts": len(accounts)})
                if (
                    settings.backup_enabled
                    and settings.backup_interval_minutes > 0
                    and now - self.last_backup_run_at >= settings.backup_interval_minutes * 60
                ):
                    self.backup_accounts_now(trigger_source="scheduled")
            except Exception:
                pass
            self.scheduler_stop.wait(30)

    def login_worker(self) -> None:
        while True:
            account = self.login_q.get()
            with self.lock:
                self.login_busy_email = account.email
                account.status = "登录中"
            success, method, err = probe_account_login(account)
            with self.lock:
                if success:
                    account.status = "登录成功"
                    account.auth_method = method or "-"
                    account.last_error = ""
                    self.enqueue_receive(account)
                    self.log_event("info", "auth", "login_success", account.email, "邮箱登录成功", {"method": method or "-"})
                else:
                    account.status = "登录失败"
                    account.last_error = err
                    self.log_event("error", "auth", "login_failed", account.email, "邮箱登录失败", {"error": err})
                account.last_check = format_shanghai_time(dt.datetime.now())
                self._save_accounts_state()
                self.login_done += 1
                self.login_busy_email = ""
                self.queued_login.discard(account.email)

    def receive_worker(self) -> None:
        while True:
            account = self.receive_q.get()
            with self.lock:
                self.receive_busy_email = account.email
                account.status = "收信中"
                existing_mails = list(account.mails)
                local_read_keys = set(self.local_read_keys)
            unseen, mails, message = fetch_mails_once(account, local_read_keys, existing_mails)
            with self.lock:
                account.unseen_count = unseen
                account.mails = mails
                account.last_check = format_shanghai_time(dt.datetime.now())
                if "成功" in message:
                    account.status = "登录成功"
                    account.last_error = ""
                    self.log_event("info", "mail_fetch", "receive_success", account.email, "收件成功", {"unseen": unseen, "method": account.auth_method})
                else:
                    account.status = "收信失败"
                    account.last_error = message
                    self.log_event("error", "mail_fetch", "receive_failed", account.email, "收件失败", {"error": message})
                self.storage.save_mail_cache(account)
                self._save_accounts_state()
                self.rebuild_mail_pool()
                self.receive_done += 1
                self.receive_busy_email = ""
                self.queued_receive.discard(account.email)

    def body_worker(self) -> None:
        while True:
            account, item = self.body_q.get()
            with self.lock:
                self.body_tasks[item.local_key] = BodyTask(
                    state="downloading",
                    status="正在下载正文",
                )

            def progress_callback(downloaded: int, total: int, speed_kb_s: float) -> None:
                with self.lock:
                    task = self.body_tasks.setdefault(item.local_key, BodyTask())
                    task.state = "downloading"
                    task.downloaded = downloaded
                    task.total = total
                    task.speed_kb_s = speed_kb_s
                    task.status = "正在下载正文"

            body, status, size, duration = fetch_mail_body(
                account,
                item.msg_id,
                item.folder,
                item.source,
                progress_callback=progress_callback,
            )
            with self.lock:
                task = self.body_tasks.setdefault(item.local_key, BodyTask())
                task.size = size
                task.duration = duration
                task.status = status
                if status == "OK":
                    item.body_text = body
                    task.state = "done"
                    task.downloaded = size
                    task.total = size
                    task.status = "正文已缓存"
                    self.storage.save_mail_cache(account)
                    self.log_event("info", "mail_body", "load_success", item.local_key, "邮件正文加载成功", {"source": item.source, "size": size})
                else:
                    task.state = "error"
                    self.log_event("error", "mail_body", "load_failed", item.local_key, "邮件正文加载失败", {"error": status, "source": item.source})
                self.queued_body.discard(item.local_key)
