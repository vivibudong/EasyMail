from __future__ import annotations

import datetime as dt
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import html
import imaplib
import json
import re
import time
from urllib.parse import quote
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import DEFAULT_IMPORT_DELIMITERS, MailAccount, MailItem

OAUTH_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
GRAPH_SCOPE = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read offline_access"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
EMAIL_PATTERN = re.compile(r"^[^\s@<>'\",;|]+@[^\s@<>'\",;|]+\.[^\s@<>'\",;|]+$")


def decode_text(raw_value: Optional[str]) -> str:
    if not raw_value:
        return ""
    parts = []
    for value, charset in decode_header(raw_value):
        if isinstance(value, bytes):
            encoding = charset or "utf-8"
            try:
                parts.append(value.decode(encoding, errors="replace"))
            except LookupError:
                parts.append(value.decode("utf-8", errors="replace"))
        else:
            parts.append(value)
    return "".join(parts).strip()


def parse_email_date(raw_date: str) -> dt.datetime:
    if not raw_date:
        return dt.datetime(1970, 1, 1)
    try:
        value = parsedate_to_datetime(raw_date)
        if value.tzinfo is not None:
            return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.replace(tzinfo=ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    except Exception:
        return dt.datetime(1970, 1, 1)


def format_shanghai_time(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def extract_body_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition.lower():
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace").strip()
                except LookupError:
                    return payload.decode("utf-8", errors="replace").strip()
        return "(该邮件没有可读纯文本正文)"
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except LookupError:
        return payload.decode("utf-8", errors="replace").strip()


def _build_import_patterns(import_delimiters: list[str]) -> list[str]:
    patterns: list[str] = []
    seen: set[str] = set()
    legacy_patterns = {
        "---": r"-{3,}",
        "-{3,}": r"-{3,}",
        "||": r"\|\|",
        r"\|\|": r"\|\|",
        "|": r"\|",
        r"\|": r"\|",
        ",": ",",
        ";": ";",
        r"\t": r"\t",
        "\t": r"\t",
        "tab": r"\t",
        "TAB": r"\t",
    }
    for raw_delimiter in [*import_delimiters, *DEFAULT_IMPORT_DELIMITERS]:
        value = str(raw_delimiter or "").strip()
        if not value:
            continue
        candidate_patterns: list[str] = []
        if value in legacy_patterns:
            candidate_patterns.append(legacy_patterns[value])
        else:
            literal_value = value.replace(r"\t", "\t").replace(r"\|", "|")
            candidate_patterns.append(re.escape(literal_value))
            if any(char in value for char in ["\\", "{", "}", "[", "]", "(", ")", "+", "*", "?"]):
                candidate_patterns.append(value)
        for pattern in candidate_patterns:
            wrapped = rf"\s*(?:{pattern})\s*"
            if wrapped not in seen:
                seen.add(wrapped)
                patterns.append(wrapped)
    return patterns


def parse_line_to_account(
    line: str, delimiter_regex: str, comment_prefix: str
) -> tuple[Optional[MailAccount], int]:
    source = line.strip()
    if not source:
        return None, 0
    if comment_prefix and source.startswith(comment_prefix):
        return None, 0
    parts = [part.strip() for part in re.split(delimiter_regex, source) if part.strip()]
    if not parts:
        return None, 0
    email_addr = parts[0]
    if not EMAIL_PATTERN.fullmatch(email_addr):
        return None, len(parts)
    return (
        MailAccount(
            email=email_addr,
            password=parts[1] if len(parts) > 1 else "",
            auth_code_or_client_id=parts[2] if len(parts) > 2 else "",
            token=parts[3] if len(parts) > 3 else "",
        ),
        len(parts),
    )


def parse_text_to_accounts(
    content: str,
    *,
    import_delimiters: list[str],
    comment_prefix: str,
    skip_first_line: bool,
) -> list[MailAccount]:
    lines = content.splitlines()
    if skip_first_line and lines:
        lines = lines[1:]

    presets = _build_import_patterns(import_delimiters)
    best_items: list[MailAccount] = []
    best_score = (-1, -1, -1)
    for regex in presets:
        try:
            re.compile(regex)
        except re.error:
            continue
        parsed_items: list[MailAccount] = []
        credential_lines = 0
        field_score = 0
        for line in lines:
            item, field_count = parse_line_to_account(line, regex, comment_prefix)
            if item:
                parsed_items.append(item)
                if field_count > 1:
                    credential_lines += 1
                field_score += min(field_count, 4)
        score = (len(parsed_items), credential_lines, field_score)
        if score > best_score:
            best_score = score
            best_items = parsed_items
    return best_items


def get_access_token_by_refresh_token(
    refresh_token: str,
    client_id: str,
    scope: str = OAUTH_SCOPE,
    tenant: str = "consumers",
) -> tuple[Optional[str], int, str, str]:
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    body = urlencode(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": scope,
        }
    ).encode("utf-8")
    request = Request(token_url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        access_token = data.get("access_token", "")
        expires_in = int(data.get("expires_in", 3600))
        next_refresh_token = str(data.get("refresh_token", "") or "")
        if access_token:
            return access_token, expires_in, "refresh_token换取access_token成功", next_refresh_token
        return None, 0, f"token接口无access_token: {raw[:220]}", ""
    except Exception as exc:
        return None, 0, str(exc), ""


def get_oauth_access_token(account: MailAccount) -> tuple[Optional[str], str]:
    now = time.time()
    if account.cached_access_token and now < account.cached_access_expire_at - 60:
        return account.cached_access_token, "OAuth2刷新令牌(缓存)"
    token = account.token.strip()
    client_id = account.auth_code_or_client_id.strip()
    if not token:
        return None, "缺少第4段令牌"
    if not client_id:
        return None, "缺少第3段ClientID"
    access_token, expires_in, message, next_refresh_token = get_access_token_by_refresh_token(
        token,
        client_id,
        scope=OAUTH_SCOPE,
    )
    if access_token:
        account.cached_access_token = access_token
        account.cached_access_expire_at = now + max(300, expires_in)
        if next_refresh_token:
            account.token = next_refresh_token
        return access_token, "OAuth2刷新令牌"
    return None, message


def get_graph_access_token(account: MailAccount) -> tuple[Optional[str], str]:
    now = time.time()
    if account.cached_graph_access_token and now < account.cached_graph_access_expire_at - 60:
        return account.cached_graph_access_token, "Graph刷新令牌(缓存)"
    token = account.token.strip()
    client_id = account.auth_code_or_client_id.strip()
    if not token:
        return None, "缺少第4段令牌"
    if not client_id:
        return None, "缺少第3段ClientID"
    access_token, expires_in, message, next_refresh_token = get_access_token_by_refresh_token(
        token,
        client_id,
        scope=GRAPH_SCOPE,
    )
    if access_token:
        account.cached_graph_access_token = access_token
        account.cached_graph_access_expire_at = now + max(300, expires_in)
        if next_refresh_token:
            account.token = next_refresh_token
        return access_token, "Graph刷新令牌"
    return None, message


def _is_outlook_graph_candidate(account: MailAccount) -> bool:
    email_addr = account.email.lower()
    return (
        bool(account.token.strip() and account.auth_code_or_client_id.strip())
        and (
            email_addr.endswith("@outlook.com")
            or email_addr.endswith("@hotmail.com")
            or email_addr.endswith("@live.com")
            or account.imap_host == "imap-mail.outlook.com"
        )
    )


def _graph_request_json(
    path: str,
    access_token: str,
    timeout: int = 20,
) -> tuple[Optional[dict], str]:
    request = Request(
        f"{GRAPH_BASE_URL}{path}",
        method="GET",
    )
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Accept", "application/json")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}, "OK"
    except Exception as exc:
        return None, str(exc)


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _graph_folder_candidates() -> list[tuple[str, str]]:
    return [
        ("inbox", "收件箱"),
        ("junkemail", "垃圾邮件"),
        ("deleteditems", "已删除"),
    ]


def fetch_mails_via_graph(
    account: MailAccount,
    local_read_keys: Optional[set[str]],
    existing_mails: Optional[list[MailItem]],
) -> tuple[int, list[MailItem], str]:
    access_token, message = get_graph_access_token(account)
    if not access_token:
        return 0, existing_mails or [], message
    existing_by_key: dict[str, MailItem] = {}
    if existing_mails:
        for item in existing_mails:
            if item.source == "graph":
                existing_by_key[item.local_key] = item
    merged_unseen_total = 0
    for folder_id, folder_name in _graph_folder_candidates():
        path = (
            f"/me/mailFolders/{quote(folder_id)}/messages"
            "?$top=50"
            "&$select=id,subject,from,receivedDateTime,isRead"
            "&$orderby=receivedDateTime desc"
        )
        payload, error = _graph_request_json(path, access_token)
        if payload is None:
            continue
        messages = payload.get("value", [])
        if not isinstance(messages, list):
            continue
        for message_item in messages:
            remote_id = str(message_item.get("id", "")).strip()
            if not remote_id:
                continue
            local_key = f"{account.email}|graph|{folder_id}|{remote_id}"
            if local_key in existing_by_key:
                existing_item = existing_by_key[local_key]
                existing_item.folder = folder_name
                if local_read_keys and local_key in local_read_keys:
                    existing_item.is_unread = False
                else:
                    existing_item.is_unread = not bool(message_item.get("isRead", False))
                if existing_item.is_unread:
                    merged_unseen_total += 1
                continue
            sender = ""
            from_payload = message_item.get("from", {})
            if isinstance(from_payload, dict):
                email_address = from_payload.get("emailAddress", {})
                if isinstance(email_address, dict):
                    sender = (
                        email_address.get("name")
                        or email_address.get("address")
                        or ""
                    )
            received_at = str(message_item.get("receivedDateTime", "")).strip()
            date_value = parse_email_date(received_at.replace("T", " ").replace("Z", " +0000"))
            is_unread = not bool(message_item.get("isRead", False))
            if local_read_keys and local_key in local_read_keys:
                is_unread = False
            if is_unread:
                merged_unseen_total += 1
            new_item = MailItem(
                account_email=account.email,
                msg_id=remote_id.encode(),
                folder=folder_name,
                local_key=local_key,
                subject=str(message_item.get("subject") or "(无主题)"),
                from_text=sender or "(未知发件人)",
                date_text=format_shanghai_time(date_value),
                date_value=date_value,
                source="graph",
                is_unread=is_unread,
                body_text="",
            )
            existing_by_key[local_key] = new_item
    if not existing_by_key:
        return 0, existing_mails or [], "Graph API 未获取到可用邮件，已回退 IMAP"
    merged = list(existing_by_key.values())
    merged.sort(key=lambda item: item.date_value, reverse=True)
    account.auth_method = "Graph API"
    return merged_unseen_total, merged, "Graph收信成功"


def build_auth_candidates(account: MailAccount) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    token = account.token.strip()
    third = account.auth_code_or_client_id.strip()
    if token:
        if token.startswith("eyJ"):
            candidates.append(("XOAUTH2", token, "OAuth2访问令牌"))
        else:
            access_token, message = get_oauth_access_token(account)
            if access_token:
                candidates.append(("XOAUTH2", access_token, message))
            else:
                candidates.append(("ERROR", message, "OAuth2刷新失败"))
    if third:
        candidates.append(("LOGIN", third, "第三段凭据"))
    if account.password:
        candidates.append(("LOGIN", account.password, "密码"))
    return candidates


def connect_imap(account: MailAccount) -> tuple[Optional[imaplib.IMAP4_SSL], Optional[str], str]:
    candidates = build_auth_candidates(account)
    if not candidates:
        return None, None, "缺少可用登录凭据"
    errors: list[str] = []
    for mode, secret, label in candidates:
        if mode == "ERROR":
            errors.append(f"{label}: {secret}")
            continue
        try:
            client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=15)
            if mode == "LOGIN":
                client.login(account.email, secret)
            else:
                auth_string = f"user={account.email}\x01auth=Bearer {secret}\x01\x01"
                client.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
            return client, label, "登录成功"
        except Exception as exc:
            text = str(exc)
            if "BasicAuthBlocked" in text:
                text = f"{text}（微软已禁用基础认证，请使用OAuth2）"
            errors.append(f"{label}: {text}")
    return None, None, "；".join(errors)


def fetch_mails_once(
    account: MailAccount,
    local_read_keys: Optional[set[str]],
    existing_mails: Optional[list[MailItem]],
) -> tuple[int, list[MailItem], str]:
    if _is_outlook_graph_candidate(account):
        graph_unseen, graph_mails, graph_message = fetch_mails_via_graph(
            account,
            local_read_keys,
            existing_mails,
        )
        if "成功" in graph_message:
            return graph_unseen, graph_mails, graph_message
    client, method, err = connect_imap(account)
    if client is None:
        return 0, existing_mails or [], err
    account.auth_method = method or "-"
    try:
        folders: list[str] = []
        try:
            typ, lines = client.list()
            if typ == "OK" and lines:
                for line in lines:
                    text = line.decode(errors="ignore") if isinstance(line, bytes) else str(line)
                    match = re.search(r'"([^"]+)"\s*$', text)
                    if not match:
                        continue
                    name = match.group(1)
                    lowered = name.lower()
                    if name.upper() == "INBOX" or any(
                        key in lowered for key in ["junk", "spam", "deleted", "trash"]
                    ):
                        if name not in folders:
                            folders.append(name)
        except Exception:
            pass
        if not folders:
            folders = [
                "INBOX",
                "Junk",
                "Junk Email",
                "Junk E-Mail",
                "Spam",
                "Deleted Items",
                "Trash",
            ]

        existing_by_key: dict[str, MailItem] = {}
        if existing_mails:
            for item in existing_mails:
                existing_by_key[item.local_key] = item

        unseen_total = 0
        for folder in folders:
            try:
                typ, _ = client.select(f'"{folder}"', readonly=True)
                if typ != "OK":
                    continue
            except Exception:
                continue

            unseen_typ, unseen_data = client.search(None, "UNSEEN")
            unseen_ids = (
                unseen_data[0].split()
                if unseen_typ == "OK" and unseen_data and unseen_data[0]
                else []
            )
            unseen_total += len(unseen_ids)

            all_typ, all_data = client.search(None, "ALL")
            if all_typ != "OK":
                continue
            all_ids = all_data[0].split() if all_data and all_data[0] else []

            for msg_id in all_ids:
                msg_id_str = msg_id.decode(errors="ignore")
                local_key = f"{account.email}|{folder}|{msg_id_str}"
                if local_key in existing_by_key:
                    continue
                fetch_typ, fetch_data = client.fetch(
                    msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE FROM)])"
                )
                if fetch_typ != "OK" or not fetch_data:
                    continue
                header_block = b""
                for item in fetch_data:
                    if isinstance(item, tuple) and isinstance(item[1], bytes):
                        header_block += item[1]
                if not header_block:
                    continue
                msg = email.message_from_bytes(header_block)
                is_unread = True
                if local_read_keys and local_key in local_read_keys:
                    is_unread = False
                new_item = MailItem(
                    account_email=account.email,
                    msg_id=msg_id,
                    folder=folder,
                    local_key=local_key,
                    subject=decode_text(msg.get("Subject")) or "(无主题)",
                    from_text=decode_text(msg.get("From")) or "(未知发件人)",
                    date_text="",
                    date_value=parse_email_date(decode_text(msg.get("Date"))),
                    source="imap",
                    is_unread=is_unread,
                    body_text="",
                )
                new_item.date_text = format_shanghai_time(new_item.date_value)
                existing_by_key[local_key] = new_item

        client.logout()
        merged = list(existing_by_key.values())
        merged.sort(key=lambda item: item.date_value, reverse=True)
        return unseen_total, merged, "收信成功"
    except Exception as exc:
        return (
            0,
            list(existing_by_key.values()) if "existing_by_key" in locals() else (existing_mails or []),
            str(exc),
        )


def fetch_mail_body(
    account: MailAccount,
    msg_id: bytes,
    folder: str,
    source: str = "imap",
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> tuple[str, str, int, float]:
    if source == "graph":
        access_token, error = get_graph_access_token(account)
        if not access_token:
            return "", error, 0, 0.0
        remote_id = msg_id.decode(errors="ignore")
        payload, request_error = _graph_request_json(
            f"/me/messages/{quote(remote_id)}?$select=body,bodyPreview",
            access_token,
        )
        if payload is None:
            return "", request_error, 0, 0.0
        body_payload = payload.get("body", {})
        if isinstance(body_payload, dict):
            content = str(body_payload.get("content", "") or "")
            content_type = str(body_payload.get("contentType", "text") or "text").lower()
            body_text = _html_to_text(content) if content_type == "html" else content.strip()
            return body_text, "OK", len(content.encode("utf-8", errors="ignore")), 0.01
        preview = str(payload.get("bodyPreview", "") or "")
        return preview, "OK", len(preview.encode("utf-8", errors="ignore")), 0.01

    client, _, err = connect_imap(account)
    if client is None:
        return "", err, 0, 0.0
    try:
        started = time.perf_counter()
        try:
            typ, _ = client.select(f'"{folder}"', readonly=True)
        except Exception:
            typ, _ = client.select('"INBOX"', readonly=True)
        if typ != "OK":
            client.logout()
            return "", f"无法选择文件夹: {folder}", 0, 0.0

        size_typ, size_data = client.fetch(msg_id, "(RFC822.SIZE)")
        total_size = 0
        if size_typ == "OK" and size_data:
            for item in size_data:
                if isinstance(item, tuple) and isinstance(item[0], bytes):
                    match = re.search(rb"RFC822\.SIZE (\d+)", item[0])
                    if match:
                        total_size = int(match.group(1))
                        break

        raw_bytes = b""
        downloaded = 0
        chunk_size = 65536

        if total_size > 0:
            while downloaded < total_size:
                fetch_typ, fetch_data = client.fetch(
                    msg_id, f"(BODY.PEEK[]<{downloaded}.{chunk_size}>)"
                )
                if fetch_typ != "OK" or not fetch_data:
                    break
                received = b""
                for item in fetch_data:
                    if isinstance(item, tuple) and isinstance(item[1], bytes):
                        received += item[1]
                if not received:
                    break
                raw_bytes += received
                downloaded += len(received)
                if progress_callback is not None:
                    elapsed = max(0.001, time.perf_counter() - started)
                    speed = (downloaded / 1024.0) / elapsed
                    progress_callback(downloaded, total_size, speed)
        else:
            fetch_typ, fetch_data = client.fetch(msg_id, "(BODY.PEEK[])")
            if fetch_typ != "OK" or not fetch_data:
                client.logout()
                return "", "读取邮件正文失败", 0, 0.0
            for item in fetch_data:
                if isinstance(item, tuple) and isinstance(item[1], bytes):
                    raw_bytes += item[1]

        client.logout()
        if not raw_bytes:
            return "", "邮件正文为空", 0, 0.0
        msg = email.message_from_bytes(raw_bytes)
        duration = max(0.001, time.perf_counter() - started)
        return extract_body_text(msg), "OK", len(raw_bytes), duration
    except Exception as exc:
        return "", str(exc), 0, 0.0
