from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Optional

IMAP_HOST = "imap-mail.outlook.com"
IMAP_PORT = 993
DEFAULT_IMPORT_DELIMITERS = ["---", "||", "|", ",", ";", r"\t"]


@dataclass
class MailItem:
    account_email: str
    msg_id: bytes
    folder: str
    local_key: str
    subject: str
    from_text: str
    date_text: str
    date_value: dt.datetime
    source: str = "imap"
    is_unread: bool = False
    is_starred: bool = False
    body_text: str = ""
    body_html: str = ""
    verification_codes: list[dict] = field(default_factory=list)
    has_attachments: bool = False
    attachments: list[dict] = field(default_factory=list)


@dataclass
class MailAccount:
    email: str
    password: str = ""
    auth_code_or_client_id: str = ""
    token: str = ""
    imap_host: str = IMAP_HOST
    imap_port: int = IMAP_PORT
    status: str = "未登录"
    last_check: str = "-"
    unseen_count: int = 0
    last_error: str = ""
    auth_method: str = "-"
    mails: list[MailItem] = field(default_factory=list)
    cached_access_token: str = ""
    cached_access_expire_at: float = 0.0
    cached_graph_access_token: str = ""
    cached_graph_access_expire_at: float = 0.0
    cached_graph_scope: str = ""
    last_token_refresh_at: str = ""
    last_token_success_at: str = ""
    last_token_rotated_at: str = ""
    token_expires_at: str = ""
    flag_color: str = ""
    group_name: str = "未分组"
    tags: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class GroupDefinition:
    name: str
    color: str = "#D6EAF8"
    priority: int = 100
    locked: bool = False


@dataclass
class TagDefinition:
    name: str
    color: str = "#BFDBFE"
    priority: int = 100


@dataclass
class AppSettings:
    auto_receive_interval: int = 120
    import_delimiters: list[str] = field(
        default_factory=lambda: DEFAULT_IMPORT_DELIMITERS.copy()
    )
    txt_comment_prefix: str = "#"
    txt_skip_first_line: bool = False
    startup_auto_login: bool = True
    mail_list_limit: int = 0
    mark_read_on_open: bool = True
    custom_groups: list[GroupDefinition] = field(default_factory=list)
    custom_tags: list[TagDefinition] = field(default_factory=list)
    auto_receive_enabled: bool = False
    auto_receive_interval_minutes: int = 30
    auto_receive_group_intervals: dict[str, int] = field(default_factory=dict)
    auto_receive_pause_failed: bool = True
    auto_receive_incremental: bool = True
    token_refresh_enabled: bool = False
    token_refresh_interval_minutes: int = 360
    token_refresh_mode: str = "expiry"
    token_refresh_window_days: int = 7
    token_refresh_include_unknown_expiry: bool = True
    backup_enabled: bool = False
    backup_interval_minutes: int = 1440
    backup_directory: str = "backups"
    backup_keep_count: int = 10
    oauth_client_id: str = ""
    oauth_redirect_uri: str = "http://localhost:8765/callback"
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_mail_mode: str = "hourly"
    telegram_mail_group: str = "__all__"
    telegram_mail_groups: list[str] = field(default_factory=list)
    telegram_mail_summary_minutes: int = 60
    telegram_notify_backup: bool = False
    translate_provider: str = "free"
    translate_api_key: str = ""
    translate_model: str = ""
    translate_fallback_to_free: bool = True


@dataclass
class BodyTask:
    state: str = "idle"
    downloaded: int = 0
    total: int = 0
    speed_kb_s: float = 0.0
    status: str = ""
    size: int = 0
    duration: float = 0.0


def mail_cache_filename(email_addr: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", email_addr)
    return f"{safe}.json"


def mail_item_to_dict(m: MailItem) -> dict:
    return {
        "account_email": m.account_email,
        "msg_id": m.msg_id.decode(errors="ignore"),
        "folder": m.folder,
        "local_key": m.local_key,
        "source": m.source,
        "subject": m.subject,
        "from_text": m.from_text,
        "date_text": m.date_text,
        "date_value": m.date_value.isoformat(),
        "is_unread": m.is_unread,
        "is_starred": m.is_starred,
        "body_text": m.body_text,
        "body_html": m.body_html,
        "verification_codes": m.verification_codes,
        "has_attachments": bool(m.has_attachments or bool(m.attachments)),
        "attachments": m.attachments,
    }


def mail_item_from_dict(data: dict) -> Optional[MailItem]:
    try:
        msg_id_str = str(data.get("msg_id", ""))
        if not msg_id_str:
            return None
        date_str = str(data.get("date_value", ""))
        date_value = (
            dt.datetime.fromisoformat(date_str)
            if date_str
            else dt.datetime(1970, 1, 1)
        )
        attachments = [item for item in data.get("attachments", []) if isinstance(item, dict)]
        return MailItem(
            account_email=str(data.get("account_email", "")),
            msg_id=msg_id_str.encode(),
            folder=str(data.get("folder", "INBOX")),
            local_key=str(data.get("local_key", "")),
            source=str(data.get("source", "imap") or "imap"),
            subject=str(data.get("subject", "(无主题)")),
            from_text=str(data.get("from_text", "")),
            date_text=str(data.get("date_text", "")),
            date_value=date_value,
            is_unread=bool(data.get("is_unread", True)),
            is_starred=bool(data.get("is_starred", False)),
            body_text=str(data.get("body_text", "")),
            body_html=str(data.get("body_html", "")),
            verification_codes=[item for item in data.get("verification_codes", []) if isinstance(item, dict)],
            has_attachments=bool(data.get("has_attachments", False) or bool(attachments)),
            attachments=attachments,
        )
    except Exception:
        return None


def account_to_dict(a: MailAccount) -> dict:
    persisted_status = a.status
    if persisted_status in {"登录中", "收信中"}:
        persisted_status = "登录成功" if (a.cached_access_token or a.cached_graph_access_token or a.auth_method not in {"", "-"}) else "已缓存"
    return {
        "email": a.email,
        "password": a.password,
        "auth_code_or_client_id": a.auth_code_or_client_id,
        "token": a.token,
        "imap_host": a.imap_host,
        "imap_port": a.imap_port,
        "status": persisted_status,
        "last_check": a.last_check,
        "unseen_count": a.unseen_count,
        "last_error": a.last_error,
        "auth_method": a.auth_method,
        "cached_access_token": a.cached_access_token,
        "cached_access_expire_at": a.cached_access_expire_at,
        "cached_graph_access_token": a.cached_graph_access_token,
        "cached_graph_access_expire_at": a.cached_graph_access_expire_at,
        "cached_graph_scope": a.cached_graph_scope,
        "last_token_refresh_at": a.last_token_refresh_at,
        "last_token_success_at": a.last_token_success_at,
        "last_token_rotated_at": a.last_token_rotated_at,
        "token_expires_at": a.token_expires_at,
        "flag_color": a.flag_color,
        "group_name": a.group_name,
        "tags": a.tags,
        "note": a.note,
    }


def account_from_dict(data: dict) -> Optional[MailAccount]:
    email_addr = str(data.get("email", "")).strip()
    if not email_addr or "@" not in email_addr:
        return None
    try:
        port = int(data.get("imap_port", IMAP_PORT))
    except Exception:
        port = IMAP_PORT
    raw_status = str(data.get("status", "") or "").strip()
    cached_access = str(data.get("cached_access_token", "") or "")
    cached_graph = str(data.get("cached_graph_access_token", "") or "")
    auth_method = str(data.get("auth_method", "-") or "-")
    if raw_status in {"登录中", "收信中"}:
        restored_status = "登录成功" if (cached_access or cached_graph or auth_method not in {"", "-"}) else "待登录"
    elif raw_status in {"登录成功", "登录失败", "收信失败", "已缓存", "待登录", "未登录"}:
        restored_status = raw_status
    elif cached_access or cached_graph:
        restored_status = "登录成功"
    else:
        restored_status = "待登录"
    try:
        unseen_count = max(0, int(data.get("unseen_count", 0) or 0))
    except Exception:
        unseen_count = 0
    return MailAccount(
        email=email_addr,
        password=str(data.get("password", "")),
        auth_code_or_client_id=str(data.get("auth_code_or_client_id", "")),
        token=str(data.get("token", "")),
        imap_host=str(data.get("imap_host", IMAP_HOST)),
        imap_port=port,
        status=restored_status,
        last_check=str(data.get("last_check", "-") or "-"),
        unseen_count=unseen_count,
        last_error=str(data.get("last_error", "") or ""),
        auth_method=auth_method,
        cached_access_token=cached_access,
        cached_access_expire_at=float(data.get("cached_access_expire_at", 0.0) or 0.0),
        cached_graph_access_token=cached_graph,
        cached_graph_access_expire_at=float(data.get("cached_graph_access_expire_at", 0.0) or 0.0),
        cached_graph_scope=str(data.get("cached_graph_scope", "") or ""),
        last_token_refresh_at=str(data.get("last_token_refresh_at", "") or ""),
        last_token_success_at=str(data.get("last_token_success_at", "") or ""),
        last_token_rotated_at=str(data.get("last_token_rotated_at", "") or ""),
        token_expires_at=str(data.get("token_expires_at", "") or ""),
        flag_color=str(data.get("flag_color", "")),
        group_name=str(data.get("group_name", "未分组") or "未分组"),
        tags=[str(item) for item in data.get("tags", []) if str(item).strip()],
        note=str(data.get("note", "") or ""),
    )


def settings_to_dict(settings: AppSettings) -> dict:
    return {
        "auto_receive_interval": settings.auto_receive_interval,
        "import_delimiters": normalize_import_delimiters(settings.import_delimiters),
        "txt_comment_prefix": settings.txt_comment_prefix,
        "txt_skip_first_line": settings.txt_skip_first_line,
        "startup_auto_login": settings.startup_auto_login,
        "mail_list_limit": settings.mail_list_limit,
        "mark_read_on_open": settings.mark_read_on_open,
        "custom_groups": [
            {"name": item.name, "color": item.color, "priority": item.priority, "locked": item.locked}
            for item in settings.custom_groups
        ],
        "custom_tags": [
            {"name": item.name, "color": item.color, "priority": item.priority}
            for item in settings.custom_tags
        ],
        "auto_receive_enabled": settings.auto_receive_enabled,
        "auto_receive_interval_minutes": settings.auto_receive_interval_minutes,
        "auto_receive_group_intervals": normalize_group_receive_intervals(settings.auto_receive_group_intervals),
        "auto_receive_pause_failed": settings.auto_receive_pause_failed,
        "auto_receive_incremental": settings.auto_receive_incremental,
        "token_refresh_enabled": settings.token_refresh_enabled,
        "token_refresh_interval_minutes": settings.token_refresh_interval_minutes,
        "token_refresh_mode": settings.token_refresh_mode if settings.token_refresh_mode in {"expiry", "interval"} else "expiry",
        "token_refresh_window_days": max(1, min(60, int(settings.token_refresh_window_days or 7))),
        "token_refresh_include_unknown_expiry": bool(settings.token_refresh_include_unknown_expiry),
        "backup_enabled": settings.backup_enabled,
        "backup_interval_minutes": settings.backup_interval_minutes,
        "backup_directory": settings.backup_directory,
        "backup_keep_count": settings.backup_keep_count,
        "oauth_client_id": settings.oauth_client_id,
        "oauth_redirect_uri": settings.oauth_redirect_uri,
        "telegram_enabled": settings.telegram_enabled,
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_chat_id": settings.telegram_chat_id,
        "telegram_mail_mode": settings.telegram_mail_mode,
        "telegram_mail_group": settings.telegram_mail_group,
        "telegram_mail_groups": normalize_telegram_mail_groups(settings.telegram_mail_groups),
        "telegram_mail_summary_minutes": settings.telegram_mail_summary_minutes,
        "telegram_notify_backup": settings.telegram_notify_backup,
        "translate_provider": settings.translate_provider,
        "translate_api_key": settings.translate_api_key,
        "translate_model": settings.translate_model,
        "translate_fallback_to_free": settings.translate_fallback_to_free,
    }


def normalize_import_delimiters(values: object) -> list[str]:
    raw_values = values if isinstance(values, list) else []
    legacy_map = {
        "-{3,}": "---",
        r"\|\|": "||",
        r"\|": "|",
        r"\t": r"\t",
        "\t": r"\t",
        "tab": r"\t",
        "TAB": r"\t",
    }
    cleaned: list[str] = []
    for item in raw_values:
        value = str(item).strip()
        if not value:
            continue
        value = legacy_map.get(value, value)
        if value not in cleaned:
            cleaned.append(value)
    return cleaned or DEFAULT_IMPORT_DELIMITERS.copy()


def normalize_group_receive_intervals(values: object) -> dict[str, int]:
    if not isinstance(values, dict):
        return {}
    cleaned: dict[str, int] = {}
    for raw_key, raw_val in values.items():
        name = str(raw_key or "").strip()
        if not name:
            continue
        try:
            minutes = int(raw_val)
        except Exception:
            continue
        if minutes <= 0:
            cleaned[name] = 0
        else:
            cleaned[name] = max(30, min(10080, minutes))
    return cleaned


def normalize_telegram_mail_groups(values: object) -> list[str]:
    raw_values = values if isinstance(values, list) else []
    cleaned: list[str] = []
    for item in raw_values:
        value = str(item).strip()
        if not value or value in cleaned:
            continue
        cleaned.append(value)
    return cleaned


def settings_from_dict(data: dict) -> AppSettings:
    raw_groups = data.get("custom_groups", [])
    group_items: list[GroupDefinition] = []
    for item in raw_groups:
        if isinstance(item, str):
            name = item.strip()
            if name and name != "未分组":
                group_items.append(GroupDefinition(name=name))
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name and name != "未分组":
                group_items.append(
                    GroupDefinition(
                        name=name,
                        color=str(item.get("color", "#D6EAF8") or "#D6EAF8"),
                        priority=max(1, min(999, int(item.get("priority", 100) or 100))),
                        locked=bool(item.get("locked", False)),
                    )
                )

    raw_tags = data.get("custom_tags", [])
    tag_items: list[TagDefinition] = []
    for item in raw_tags:
        if isinstance(item, str):
            name = item.strip()
            if name:
                tag_items.append(TagDefinition(name=name))
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                tag_items.append(
                    TagDefinition(
                        name=name,
                        color=str(item.get("color", "#BFDBFE") or "#BFDBFE"),
                        priority=max(1, min(999, int(item.get("priority", 100) or 100))),
                    )
                )

    telegram_mail_groups = normalize_telegram_mail_groups(data.get("telegram_mail_groups", []))
    if not telegram_mail_groups and "telegram_mail_groups" not in data:
        legacy_group = str(data.get("telegram_mail_group", "") or "").strip()
        if legacy_group:
            telegram_mail_groups = [legacy_group]

    return AppSettings(
        auto_receive_interval=int(data.get("auto_receive_interval", 120) or 120),
        import_delimiters=normalize_import_delimiters(data.get("import_delimiters", DEFAULT_IMPORT_DELIMITERS)),
        txt_comment_prefix=str(data.get("txt_comment_prefix", "#")),
        txt_skip_first_line=bool(data.get("txt_skip_first_line", False)),
        startup_auto_login=bool(data.get("startup_auto_login", True)),
        mail_list_limit=int(data.get("mail_list_limit", 0) or 0),
        mark_read_on_open=bool(data.get("mark_read_on_open", True)),
        custom_groups=group_items,
        custom_tags=tag_items,
        auto_receive_enabled=bool(data.get("auto_receive_enabled", False)),
        auto_receive_interval_minutes=(
            0
            if int(data.get("auto_receive_interval_minutes", 30) if data.get("auto_receive_interval_minutes") is not None else 30) <= 0
            else max(30, int(data.get("auto_receive_interval_minutes", 30) or 30))
        ),
        auto_receive_group_intervals=normalize_group_receive_intervals(data.get("auto_receive_group_intervals", {})),
        auto_receive_pause_failed=bool(data.get("auto_receive_pause_failed", True)),
        auto_receive_incremental=bool(data.get("auto_receive_incremental", True)),
        token_refresh_enabled=bool(data.get("token_refresh_enabled", False)),
        token_refresh_interval_minutes=int(data.get("token_refresh_interval_minutes", 360) or 360),
        token_refresh_mode=(
            str(data.get("token_refresh_mode", "expiry") or "expiry").strip().lower()
            if str(data.get("token_refresh_mode", "expiry") or "expiry").strip().lower() in {"expiry", "interval"}
            else "expiry"
        ),
        token_refresh_window_days=max(1, min(60, int(data.get("token_refresh_window_days", 7) or 7))),
        token_refresh_include_unknown_expiry=bool(data.get("token_refresh_include_unknown_expiry", True)),
        backup_enabled=bool(data.get("backup_enabled", False)),
        backup_interval_minutes=int(data.get("backup_interval_minutes", 1440) or 1440),
        backup_directory=str(data.get("backup_directory", "backups") or "backups"),
        backup_keep_count=int(data.get("backup_keep_count", 10) or 10),
        oauth_client_id=str(data.get("oauth_client_id", "") or ""),
        oauth_redirect_uri=str(
            data.get("oauth_redirect_uri", "http://localhost:8765/callback")
            or "http://localhost:8765/callback"
        ),
        telegram_enabled=bool(data.get("telegram_enabled", False)),
        telegram_bot_token=str(data.get("telegram_bot_token", "") or ""),
        telegram_chat_id=str(data.get("telegram_chat_id", "") or ""),
        telegram_mail_mode=str(data.get("telegram_mail_mode", "hourly") or "hourly"),
        telegram_mail_group=str(data.get("telegram_mail_group", "__all__") or "__all__"),
        telegram_mail_groups=telegram_mail_groups,
        telegram_mail_summary_minutes=int(data.get("telegram_mail_summary_minutes", 60) or 60),
        telegram_notify_backup=bool(data.get("telegram_notify_backup", False)),
        translate_provider=str(data.get("translate_provider", "free") or "free").strip().lower(),
        translate_api_key=str(data.get("translate_api_key", "") or "").strip(),
        translate_model=str(data.get("translate_model", "") or "").strip(),
        translate_fallback_to_free=bool(data.get("translate_fallback_to_free", True)),
    )
