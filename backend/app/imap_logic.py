from __future__ import annotations

import base64
import datetime as dt
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import html
import imaplib
import json
import re
import time
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import DEFAULT_IMPORT_DELIMITERS, MailAccount, MailItem

OAUTH_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
GRAPH_SCOPE = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read offline_access"
GRAPH_READWRITE_SCOPE = "https://graph.microsoft.com/Mail.ReadWrite offline_access"
GRAPH_SEND_SCOPE = "https://graph.microsoft.com/Mail.Send offline_access"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_ROTATION_ESTIMATED_DAYS = 90
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


def format_sender_display(name: str, address: str) -> str:
    clean_name = (name or "").strip().strip('"')
    clean_address = (address or "").strip()
    if clean_name and clean_address:
        return f"{clean_name} <{clean_address}>"
    return clean_address or clean_name or "(未知发件人)"


def parse_email_date(raw_date: str) -> dt.datetime:
    if not raw_date:
        return dt.datetime(1970, 1, 1)
    text = raw_date.strip()
    try:
        if "T" in text or text.endswith("Z"):
            normalized = text.replace("Z", "+00:00")
            value = dt.datetime.fromisoformat(normalized)
            if value.tzinfo is not None:
                return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
            return value
    except Exception:
        pass
    try:
        value = parsedate_to_datetime(text)
        if value.tzinfo is not None:
            return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.replace(tzinfo=ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    except Exception:
        return dt.datetime(1970, 1, 1)


def format_shanghai_time(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _decode_part_payload(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except LookupError:
        return payload.decode("utf-8", errors="replace").strip()


def extract_body_text(msg: email.message.Message) -> str:
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition.lower():
                text_body = _decode_part_payload(part)
                if text_body:
                    if "<html" in text_body.lower() or "<table" in text_body.lower() or "<meta" in text_body.lower():
                        return _html_to_text(text_body)
                    return text_body
            if content_type == "text/html" and "attachment" not in disposition.lower() and not html_body:
                html_body = _decode_part_payload(part)
        return _html_to_text(html_body) if html_body else "(该邮件没有可读正文)"
    text_body = _decode_part_payload(msg)
    if msg.get_content_type() == "text/html" or "<html" in text_body.lower() or "<table" in text_body.lower() or "<meta" in text_body.lower():
        return _html_to_text(text_body)
    return text_body


def extract_body_html(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/html" and "attachment" not in disposition.lower():
                html_body = _decode_part_payload(part)
                if html_body:
                    return html_body
        return ""
    if msg.get_content_type() == "text/html":
        return _decode_part_payload(msg)
    text_body = _decode_part_payload(msg)
    return text_body if "<html" in text_body.lower() or "<table" in text_body.lower() else ""


def sanitize_attachment_filename(filename: str, fallback: str = "attachment") -> str:
    decoded = decode_text(filename or "").strip()
    if not decoded:
        return fallback
    cleaned = re.sub(r"[\r\n\x00]+", " ", decoded).strip()
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    return cleaned or fallback


def extract_message_attachments(
    msg: email.message.Message,
    *,
    include_content: bool = False,
) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    if not msg.is_multipart():
        return attachments
    attachment_index = 0
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = str(part.get("Content-Disposition", "") or "").lower()
        filename = part.get_filename()
        content_type = (part.get_content_type() or "application/octet-stream").lower()
        is_attachment = "attachment" in disposition
        is_inline = "inline" in disposition
        has_filename = bool(filename)
        if not (is_attachment or has_filename or (is_inline and content_type not in {"text/plain", "text/html"})):
            continue
        attachment_index += 1
        payload = part.get_payload(decode=True) or b""
        item: dict[str, Any] = {
            "id": f"attachment-{attachment_index}",
            "name": sanitize_attachment_filename(filename or "", f"attachment-{attachment_index}"),
            "content_type": content_type,
            "size": len(payload),
            "is_inline": bool(is_inline and not is_attachment),
            "content_id": str(part.get("Content-ID", "") or "").strip("<>"),
        }
        if include_content:
            item["content"] = payload
        attachments.append(item)
    return attachments


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
    scope: Optional[str] = OAUTH_SCOPE,
    tenant: str = "consumers",
) -> tuple[Optional[str], int, str, str, str]:
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if scope:
        payload["scope"] = scope
    body = urlencode(payload).encode("utf-8")
    request = Request(token_url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        access_token = data.get("access_token", "")
        expires_in = int(data.get("expires_in", 3600))
        next_refresh_token = str(data.get("refresh_token", "") or "")
        granted_scope = str(data.get("scope", "") or "")
        if access_token:
            return (
                access_token,
                expires_in,
                "refresh_token换取access_token成功",
                next_refresh_token,
                granted_scope,
            )
        return None, 0, f"token接口无access_token: {raw[:220]}", "", ""
    except Exception as exc:
        return None, 0, str(exc), "", ""


def _now_shanghai_dt() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def _record_token_success(account: MailAccount, old_token: str, next_refresh_token: str) -> bool:
    now_dt = _now_shanghai_dt()
    now_text = format_shanghai_time(now_dt)
    account.last_token_refresh_at = now_text
    account.last_token_success_at = now_text
    rotated = bool(next_refresh_token and next_refresh_token.strip() and next_refresh_token.strip() != (old_token or "").strip())
    if rotated:
        account.token = next_refresh_token.strip()
        account.last_token_rotated_at = now_text
        account.token_expires_at = format_shanghai_time(now_dt + dt.timedelta(days=TOKEN_ROTATION_ESTIMATED_DAYS))
    return rotated


def get_oauth_access_token(account: MailAccount, *, force_refresh: bool = False) -> tuple[Optional[str], str]:
    now = time.time()
    if not force_refresh and account.cached_access_token and now < account.cached_access_expire_at - 60:
        return account.cached_access_token, "OAuth2刷新令牌(缓存)"
    token = account.token.strip()
    client_id = account.auth_code_or_client_id.strip()
    if not token:
        return None, "缺少第4段令牌"
    if not client_id:
        return None, "缺少第3段ClientID"
    access_token, expires_in, message, next_refresh_token, _ = get_access_token_by_refresh_token(
        token,
        client_id,
        scope=OAUTH_SCOPE,
    )
    if access_token:
        account.cached_access_token = access_token
        account.cached_access_expire_at = now + max(300, expires_in)
        _record_token_success(account, token, next_refresh_token)
        return access_token, "OAuth2刷新令牌"
    account.last_token_refresh_at = format_shanghai_time(_now_shanghai_dt())
    return None, message


def get_graph_access_token(
    account: MailAccount,
    *,
    force_refresh: bool = False,
    required_scope: Optional[str] = None,
) -> tuple[Optional[str], str]:
    now = time.time()
    required_short = ""
    if required_scope:
        first_part = required_scope.strip().split()[0]
        required_short = first_part.rsplit("/", 1)[-1].lower()
    if not force_refresh and account.cached_graph_access_token and now < account.cached_graph_access_expire_at - 60:
        cached_scope_lower = (account.cached_graph_scope or "").lower()
        if not required_short or (required_short in cached_scope_lower):
            return account.cached_graph_access_token, "Graph刷新令牌(缓存)"
    token = account.token.strip()
    client_id = account.auth_code_or_client_id.strip()
    if not token:
        return None, "缺少第4段令牌"
    if not client_id:
        return None, "缺少第3段ClientID"
    if required_scope:
        refresh_plans = [
            (required_scope, f"Graph刷新令牌({required_short or '指定权限'})"),
            (None, "Graph刷新令牌(继承原始授权)"),
        ]
    else:
        refresh_plans = [
            (None, "Graph刷新令牌(继承原始授权)"),
            (GRAPH_SCOPE, "Graph刷新令牌(显式作用域)"),
        ]
    errors: list[str] = []
    for scope, label in refresh_plans:
        access_token, expires_in, message, next_refresh_token, granted_scope = (
            get_access_token_by_refresh_token(
                token,
                client_id,
                scope=scope,
            )
        )
        if access_token:
            _record_token_success(account, token, next_refresh_token)
            granted_lower = (granted_scope or "").lower()
            if not required_scope or "mail.read" in granted_lower or not account.cached_graph_access_token:
                account.cached_graph_access_token = access_token
                account.cached_graph_access_expire_at = now + max(300, expires_in)
                account.cached_graph_scope = granted_scope
            detail = f"{label}成功"
            if granted_scope:
                detail = f"{detail}: {granted_scope}"
            return access_token, detail
        errors.append(f"{label}: {message}")
    account.last_token_refresh_at = format_shanghai_time(_now_shanghai_dt())
    return None, "；".join(errors)


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


def _graph_api_request(
    path: str,
    access_token: str,
    *,
    method: str = "GET",
    json_body: Optional[dict[str, Any]] = None,
    timeout: int = 20,
    raw_bytes: bool = False,
) -> tuple[Any, int, dict[str, str], str]:
    normalized_path = path.replace(" ", "%20")
    data_bytes = None
    if json_body is not None:
        data_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{GRAPH_BASE_URL}{normalized_path}",
        data=data_bytes,
        method=method.upper(),
    )
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Accept", "*/*" if raw_bytes else "application/json")
    if data_bytes is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", 200) or 200
            headers = {k.lower(): v for k, v in response.headers.items()}
            raw = response.read()
        if raw_bytes:
            return raw, status_code, headers, "OK"
        if not raw:
            return {}, status_code, headers, "OK"
        text = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
            return (payload if isinstance(payload, dict) else {}), status_code, headers, "OK"
        except Exception:
            return {}, status_code, headers, "OK"
    except HTTPError as exc:
        err_headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        detail = f"HTTP {exc.code}: {err_body}" if err_body else str(exc)
        return None, int(exc.code), err_headers, detail
    except URLError as exc:
        return None, 0, {}, f"NETWORK_ERROR: {exc.reason}"
    except TimeoutError as exc:
        return None, 0, {}, f"TIMEOUT_ERROR: {exc}"
    except Exception as exc:
        return None, 0, {}, str(exc)


def _graph_request_json(
    path: str,
    access_token: str,
    timeout: int = 20,
) -> tuple[Optional[dict], str]:
    payload, status_code, _, err = _graph_api_request(path, access_token, method="GET", timeout=timeout)
    if payload is None or status_code >= 400:
        return None, err
    return payload, "OK"


def fetch_graph_attachments(account: MailAccount, remote_id: str) -> list[dict[str, Any]]:
    access_token, _ = get_graph_access_token(account)
    if not access_token:
        return []
    payload, err = _graph_request_json(
        f"/me/messages/{quote(remote_id)}/attachments?$select=id,name,contentType,size,isInline",
        access_token,
    )
    if not payload or not isinstance(payload.get("value"), list):
        return []
    attachments: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("value", []), start=1):
        if not isinstance(item, dict):
            continue
        attachments.append(
            {
                "id": str(item.get("id", "") or f"graph-att-{index}"),
                "name": sanitize_attachment_filename(str(item.get("name", "") or ""), f"attachment-{index}"),
                "content_type": str(item.get("contentType", "application/octet-stream") or "application/octet-stream").lower(),
                "size": int(item.get("size", 0) or 0),
                "is_inline": bool(item.get("isInline", False)),
                "content_id": str(item.get("contentId", "") or "").strip("<>"),
            }
        )
    return attachments


def download_graph_attachment(
    account: MailAccount,
    remote_id: str,
    attachment_id: str,
) -> tuple[Optional[bytes], str, str, str]:
    access_token, err = get_graph_access_token(account)
    if not access_token:
        return None, "", "", err
    meta_path = f"/me/messages/{quote(remote_id)}/attachments/{quote(attachment_id)}"
    metadata, status_code, _, req_err = _graph_api_request(meta_path, access_token, method="GET", timeout=30)
    if metadata is None or status_code >= 400:
        return None, "", "", req_err or "获取附件元数据失败"
    filename = sanitize_attachment_filename(str(metadata.get("name", "") or ""), "attachment")
    content_type = str(metadata.get("contentType", "application/octet-stream") or "application/octet-stream")
    raw_b64 = metadata.get("contentBytes")
    if raw_b64:
        try:
            return base64.b64decode(raw_b64), filename, content_type, "OK"
        except Exception as exc:
            return None, "", "", f"解析附件内容失败: {exc}"
    raw_data, raw_status, _, raw_err = _graph_api_request(
        f"{meta_path}/$value",
        access_token,
        method="GET",
        timeout=45,
        raw_bytes=True,
    )
    if raw_data is None or raw_status >= 400:
        return None, "", "", raw_err or "下载附件内容失败"
    return raw_data, filename, content_type, "OK"


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</td\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _is_safe_url(url: str, *, allow_mailto: bool = False, allow_data_image: bool = False) -> bool:
    decoded = html.unescape(url or "")
    normalized = re.sub(r"[\x00-\x20]+", "", decoded).lower()
    if not normalized:
        return True
    if normalized.startswith(("#", "/")):
        return not normalized.startswith("//")
    if normalized.startswith(("http://", "https://")):
        return True
    if allow_mailto and normalized.startswith("mailto:"):
        return True
    if allow_data_image and re.match(r"^data:image/(png|jpe?g|gif|webp);base64,[a-z0-9+/=]+$", normalized):
        return True
    return False


def _sanitize_mail_html(raw_html: str, allow_remote_images: bool = False) -> str:
    text = raw_html or ""
    text = re.sub(r"<!doctype[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*(meta|link|base)\b[^>]*>", "", text, flags=re.IGNORECASE)
    dangerous_tags = r"script|style|iframe|object|embed|form|input|button|textarea|select|svg|math|audio|video|source"
    text = re.sub(
        rf"<\s*({dangerous_tags})\b[^>]*>.*?</\s*\1\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(rf"<\s*/?\s*({dangerous_tags})\b[^>]*>", "", text, flags=re.IGNORECASE)
    # Strip event handlers regardless of preceding whitespace or slash
    text = re.sub(r"(?<=[\s/])on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", text)
    # Strip srcset attributes to prevent bypassing remote image blocking
    text = re.sub(r"(?<=[\s/])srcset\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", text, flags=re.IGNORECASE)

    def sanitize_url_attr(match: re.Match[str]) -> str:
        attr_name = match.group(1).lower()
        raw_val = match.group(3) if match.group(3) is not None else (match.group(4) if match.group(4) is not None else (match.group(5) or ""))
        if _is_safe_url(raw_val, allow_mailto=(attr_name == "href"), allow_data_image=(attr_name == "src")):
            return match.group(0)
        return ""

    text = re.sub(
        r"(?<=[\s/])(href|action|formaction|xlink:href)\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        sanitize_url_attr,
        text,
        flags=re.IGNORECASE,
    )

    if not allow_remote_images:
        # Block remote CSS background tracking pixels in inline styles
        text = re.sub(
            r"url\s*\(\s*['\"]?\s*(?:https?:|//)[^)]*\)",
            "none",
            text,
            flags=re.IGNORECASE,
        )

    def replace_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = re.search(r"(?<=[\s/])src\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))", tag, flags=re.IGNORECASE)
        src = html.unescape((src_match.group(2) or src_match.group(3) or src_match.group(4) or "").strip()) if src_match else ""
        if not src:
            return ""
        is_remote = bool(re.match(r"^(?:https?:)?//", src, flags=re.IGNORECASE))
        if not is_remote and not _is_safe_url(src, allow_data_image=True):
            return ""
        safe_src = html.escape(src, quote=True)
        if is_remote and not allow_remote_images:
            return f'<span class="mail-image-placeholder" data-easymail-img-src="{safe_src}">远程图片已拦截</span>'
        clean_tag = re.sub(
            r"(?<=[\s/])src\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
            f'src="{safe_src}"',
            tag,
            flags=re.IGNORECASE,
        )
        clean_tag = re.sub(r"(?<=[\s/])on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", clean_tag)
        return clean_tag

    text = re.sub(r"<\s*img\b[^>]*>", replace_img, text, flags=re.IGNORECASE)
    return text.strip()


def _graph_folder_candidates() -> list[tuple[str, str]]:
    return [
        ("inbox", "收件箱"),
        ("junkemail", "垃圾邮件"),
        ("deleteditems", "已删除"),
    ]


def _shanghai_to_utc_iso(value: dt.datetime) -> str:
    aware = value.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(dt.timezone.utc)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_mails_via_graph(
    account: MailAccount,
    local_read_keys: Optional[set[str]],
    existing_mails: Optional[list[MailItem]],
    *,
    incremental: bool = False,
) -> tuple[int, list[MailItem], str]:
    access_token, message = get_graph_access_token(account)
    if not access_token:
        return 0, existing_mails or [], message
    existing_by_key: dict[str, MailItem] = {}
    folder_latest_dt: dict[str, dt.datetime] = {}
    if existing_mails:
        for item in existing_mails:
            if item.source == "graph":
                existing_by_key[item.local_key] = item
                if item.date_value > dt.datetime(1971, 1, 1):
                    prev = folder_latest_dt.get(item.folder)
                    if prev is None or item.date_value > prev:
                        folder_latest_dt[item.folder] = item.date_value
    successful_folder_requests = 0
    for folder_id, folder_name in _graph_folder_candidates():
        filter_clause = ""
        if incremental:
            latest_dt = folder_latest_dt.get(folder_name)
            if latest_dt is not None:
                overlap_dt = latest_dt - dt.timedelta(minutes=15)
                iso_utc = _shanghai_to_utc_iso(overlap_dt)
                filter_clause = f"&$filter={quote(f'receivedDateTime ge {iso_utc}', safe='')}"
        path = (
            f"/me/mailFolders/{quote(folder_id)}/messages"
            "?$top=50"
            "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments"
            "&$orderby=receivedDateTime desc"
            f"{filter_clause}"
        )
        payload, error = _graph_request_json(path, access_token)
        if payload is None and filter_clause:
            # Fallback to unfiltered query if Graph rejects $filter
            fallback_path = (
                f"/me/mailFolders/{quote(folder_id)}/messages"
                "?$top=50"
                "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments"
                "&$orderby=receivedDateTime desc"
            )
            payload, error = _graph_request_json(fallback_path, access_token)
        if payload is None:
            continue
        successful_folder_requests += 1
        messages = payload.get("value", [])
        if not isinstance(messages, list):
            continue
        for message_item in messages:
            remote_id = str(message_item.get("id", "")).strip()
            if not remote_id:
                continue
            local_key = f"{account.email}|graph|{folder_id}|{remote_id}"
            received_at = str(message_item.get("receivedDateTime", "")).strip()
            date_value = parse_email_date(received_at)
            has_att = bool(message_item.get("hasAttachments", False))
            if local_key in existing_by_key:
                existing_item = existing_by_key[local_key]
                existing_item.folder = folder_name
                existing_item.date_value = date_value
                existing_item.date_text = format_shanghai_time(date_value)
                if has_att:
                    existing_item.has_attachments = True
                if local_read_keys and local_key in local_read_keys:
                    existing_item.is_unread = False
                else:
                    existing_item.is_unread = not bool(message_item.get("isRead", False))
                continue
            sender_name = ""
            sender_address = ""
            from_payload = message_item.get("from", {})
            if isinstance(from_payload, dict):
                email_address = from_payload.get("emailAddress", {})
                if isinstance(email_address, dict):
                    sender_name = str(email_address.get("name") or "")
                    sender_address = str(email_address.get("address") or "")
            is_unread = not bool(message_item.get("isRead", False))
            if local_read_keys and local_key in local_read_keys:
                is_unread = False
            new_item = MailItem(
                account_email=account.email,
                msg_id=remote_id.encode(),
                folder=folder_name,
                local_key=local_key,
                subject=str(message_item.get("subject") or "(无主题)"),
                from_text=format_sender_display(sender_name, sender_address),
                date_text=format_shanghai_time(date_value),
                date_value=date_value,
                source="graph",
                is_unread=is_unread,
                body_text="",
                has_attachments=has_att,
            )
            existing_by_key[local_key] = new_item
    if successful_folder_requests == 0:
        return 0, existing_mails or [], "Graph API 未获取到可用邮件，已回退 IMAP"
    merged = list(existing_by_key.values())
    merged.sort(key=lambda item: item.date_value, reverse=True)
    merged_unseen_total = sum(1 for item in merged if item.is_unread)
    account.auth_method = "Graph API"
    if not merged:
        return 0, [], "Graph收信成功（0封邮件）"
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


def probe_account_login(account: MailAccount) -> tuple[bool, str, str]:
    graph_errors: list[str] = []
    if _is_outlook_graph_candidate(account):
        access_token, message = get_graph_access_token(account)
        if access_token:
            payload, error = _graph_request_json("/me/messages?$top=1&$select=id", access_token)
            if payload is not None and isinstance(payload.get("value", []), list):
                account.auth_method = "Graph API"
                return True, "Graph API", ""
            graph_errors.append(f"Graph API: {error}")
        else:
            graph_errors.append(message)

    client, method, err = connect_imap(account)
    if client:
        try:
            client.logout()
        except Exception:
            pass
        account.auth_method = method or "-"
        return True, method or "-", ""

    if graph_errors:
        return False, "", "；".join([*graph_errors, err])
    return False, "", err


def _bodystructure_has_attachments(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    if value and isinstance(value[0], str) and value[0].upper() == "ATTACHMENT":
        return True
    for idx, item in enumerate(value[:-1]):
        if isinstance(item, str) and item.upper() in {"NAME", "FILENAME"} and value[idx + 1]:
            return True
    return any(_bodystructure_has_attachments(part) for part in value)


def _parse_imap_batch_fetch(fetch_data: Any) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    for item in fetch_data or []:
        metadata = item[0] if isinstance(item, tuple) else item
        if not isinstance(metadata, bytes):
            continue
        if re.match(rb"^\d+\s+\(", metadata):
            current = {"metadata": [], "header": b""}
            records.append(current)
        if current is None:
            continue
        meta_text = metadata.decode("utf-8", errors="replace")
        current["metadata"].append(meta_text)
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            if re.search(rb"BODY\[HEADER[^\]]*\]\s*\{\d+\}$", metadata, re.IGNORECASE):
                current["header"] = item[1]
            else:
                # BODYSTRUCTURE literals (e.g. non-ASCII filenames)
                current["metadata"][-1] = re.sub(r"\{\d+\}$", "", current["metadata"][-1])
                current["metadata"].append(json.dumps(item[1].decode("utf-8", errors="replace")))

    parsed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record["header"]:
            continue
        root: list[Any] = []
        stack: list[list[Any]] = []
        target = root
        joined_meta = " ".join(record["metadata"])
        for token in re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', joined_meta):
            if token == "(":
                child: list[Any] = []
                target.append(child)
                stack.append(target)
                target = child
            elif token == ")":
                if stack:
                    target = stack.pop()
            elif token.startswith('"') and len(token) >= 2:
                target.append(re.sub(r'\\(.)', r'\1', token[1:-1]))
            elif token.upper() == "NIL":
                target.append(None)
            else:
                target.append(token)
        if len(root) < 2 or not isinstance(root[1], list):
            continue
        kv_list = root[1]
        fields: dict[str, Any] = {}
        i = 0
        while i + 1 < len(kv_list):
            key = kv_list[i]
            val = kv_list[i + 1]
            if isinstance(key, str):
                fields[key.upper()] = val
            i += 2
        uid_val = fields.get("UID")
        if not uid_val or not str(uid_val).isdigit():
            continue
        uid_str = str(uid_val)
        flags_raw = fields.get("FLAGS")
        flags_list = flags_raw if isinstance(flags_raw, list) else []
        is_seen = any(str(flag).lower() == r"\seen" for flag in flags_list)
        has_att = _bodystructure_has_attachments(fields.get("BODYSTRUCTURE", []))
        parsed[uid_str] = {
            "header": record["header"],
            "is_seen": is_seen,
            "has_attachments": has_att,
        }
    return parsed


def fetch_mails_once(
    account: MailAccount,
    local_read_keys: Optional[set[str]],
    existing_mails: Optional[list[MailItem]],
    *,
    incremental: bool = False,
) -> tuple[int, list[MailItem], str]:
    prefer_imap_first = (
        account.auth_method not in {"", "-", "Graph API"}
        and not account.cached_graph_access_token
    )
    if _is_outlook_graph_candidate(account) and not prefer_imap_first:
        graph_unseen, graph_mails, graph_message = fetch_mails_via_graph(
            account,
            local_read_keys,
            existing_mails,
            incremental=incremental,
        )
        if "成功" in graph_message:
            return graph_unseen, graph_mails, graph_message
    client, method, err = connect_imap(account)
    if client is None:
        if prefer_imap_first and _is_outlook_graph_candidate(account):
            graph_unseen, graph_mails, graph_message = fetch_mails_via_graph(
                account,
                local_read_keys,
                existing_mails,
                incremental=incremental,
            )
            if "成功" in graph_message:
                return graph_unseen, graph_mails, graph_message
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
        folder_max_uid: dict[str, int] = {}
        if existing_mails:
            for item in existing_mails:
                existing_by_key[item.local_key] = item
                if item.source == "imap_uid":
                    uid_text = item.msg_id.decode(errors="ignore").strip()
                    if uid_text.isdigit():
                        uid_val = int(uid_text)
                        if uid_val > folder_max_uid.get(item.folder, 0):
                            folder_max_uid[item.folder] = uid_val

        for folder in folders:
            try:
                typ, _ = client.select(f'"{folder}"', readonly=True)
                if typ != "OK":
                    continue
            except Exception:
                continue

            unseen_typ, unseen_data = client.uid("search", None, "UNSEEN")
            unseen_uids = (
                unseen_data[0].split()
                if unseen_typ == "OK" and unseen_data and unseen_data[0]
                else []
            )
            unseen_uid_set = set(unseen_uids)

            # Sync unread flags on already cached UID mails in this folder
            for item in existing_by_key.values():
                if item.source == "imap_uid" and item.folder == folder:
                    if local_read_keys and item.local_key in local_read_keys:
                        item.is_unread = False
                    else:
                        item.is_unread = item.msg_id in unseen_uid_set

            max_cached_uid = folder_max_uid.get(folder, 0)
            if incremental and max_cached_uid > 0:
                all_typ, all_data = client.uid("search", None, f"UID {max_cached_uid + 1}:*")
            else:
                all_typ, all_data = client.uid("search", None, "ALL")
            if all_typ != "OK":
                continue
            all_uids = all_data[0].split() if all_data and all_data[0] else []

            missing_uids: list[bytes] = []
            for msg_uid in all_uids:
                uid_str = msg_uid.decode(errors="ignore")
                local_key = f"{account.email}|imap_uid|{folder}|{uid_str}"
                is_unread = msg_uid in unseen_uid_set
                if local_read_keys and local_key in local_read_keys:
                    is_unread = False
                if local_key in existing_by_key:
                    existing_by_key[local_key].is_unread = is_unread
                    continue
                missing_uids.append(msg_uid)

            def _build_imap_item(
                msg_uid: bytes,
                header_bytes: bytes,
                *,
                has_att: bool = False,
                is_seen_override: Optional[bool] = None,
            ) -> None:
                uid_str = msg_uid.decode(errors="ignore")
                local_key = f"{account.email}|imap_uid|{folder}|{uid_str}"
                is_unread = (not is_seen_override) if is_seen_override is not None else (msg_uid in unseen_uid_set)
                if local_read_keys and local_key in local_read_keys:
                    is_unread = False
                msg = email.message_from_bytes(header_bytes)
                raw_from = msg.get("From")
                display_name, sender_address = email.utils.parseaddr(raw_from or "")
                new_item = MailItem(
                    account_email=account.email,
                    msg_id=msg_uid,
                    folder=folder,
                    local_key=local_key,
                    subject=decode_text(msg.get("Subject")) or "(无主题)",
                    from_text=format_sender_display(decode_text(display_name), sender_address),
                    date_text="",
                    date_value=parse_email_date(decode_text(msg.get("Date"))),
                    source="imap_uid",
                    is_unread=is_unread,
                    body_text="",
                    has_attachments=has_att,
                )
                new_item.date_text = format_shanghai_time(new_item.date_value)
                existing_by_key[local_key] = new_item

            batch_size = 40
            for start_idx in range(0, len(missing_uids), batch_size):
                chunk = missing_uids[start_idx : start_idx + batch_size]
                batch_parsed: dict[str, dict[str, Any]] = {}
                try:
                    uid_set = b",".join(chunk)
                    batch_typ, batch_data = client.uid(
                        "fetch",
                        uid_set,
                        "(UID FLAGS BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])",
                    )
                    if batch_typ == "OK" and batch_data:
                        batch_parsed = _parse_imap_batch_fetch(batch_data)
                except Exception:
                    batch_parsed = {}

                for msg_uid in chunk:
                    uid_str = msg_uid.decode(errors="ignore")
                    parsed_entry = batch_parsed.get(uid_str)
                    if parsed_entry and parsed_entry.get("header"):
                        _build_imap_item(
                            msg_uid,
                            parsed_entry["header"],
                            has_att=bool(parsed_entry.get("has_attachments", False)),
                            is_seen_override=bool(parsed_entry.get("is_seen", False)),
                        )
                        continue
                    # Safe fallback to per-UID header fetch if server rejected batch or omitted UID
                    try:
                        fetch_typ, fetch_data = client.uid(
                            "fetch", msg_uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
                        )
                    except Exception:
                        continue
                    if fetch_typ != "OK" or not fetch_data:
                        continue
                    header_block = b""
                    for item in fetch_data:
                        if isinstance(item, tuple) and isinstance(item[1], bytes):
                            header_block += item[1]
                    if header_block:
                        _build_imap_item(msg_uid, header_block, has_att=False)

        merged = list(existing_by_key.values())
        merged.sort(key=lambda item: item.date_value, reverse=True)
        unseen_total = sum(1 for item in merged if item.is_unread)
        return unseen_total, merged, "收信成功"
    except Exception as exc:
        return (
            0,
            list(existing_by_key.values()) if "existing_by_key" in locals() else (existing_mails or []),
            str(exc),
        )
    finally:
        try:
            client.logout()
        except Exception:
            pass


def fetch_mail_body(
    account: MailAccount,
    msg_id: bytes,
    folder: str,
    source: str = "imap",
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    mode: str = "text",
    attachments_out: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str, int, float]:
    if source == "graph":
        access_token, error = get_graph_access_token(account)
        if not access_token:
            return "", error, 0, 0.0
        remote_id = msg_id.decode(errors="ignore")
        payload, request_error = _graph_request_json(
            f"/me/messages/{quote(remote_id)}?$select=body,bodyPreview,hasAttachments",
            access_token,
        )
        if payload is None:
            return "", request_error, 0, 0.0
        if attachments_out is not None and bool(payload.get("hasAttachments", False)):
            attachments_out[:] = fetch_graph_attachments(account, remote_id)
        body_payload = payload.get("body", {})
        if isinstance(body_payload, dict):
            content = str(body_payload.get("content", "") or "")
            content_type = str(body_payload.get("contentType", "text") or "text").lower()
            if mode == "html":
                body_text = _sanitize_mail_html(content) if content_type == "html" else f"<pre>{html.escape(content.strip())}</pre>"
            else:
                body_text = _html_to_text(content) if content_type == "html" else content.strip()
            return body_text, "OK", len(content.encode("utf-8", errors="ignore")), 0.01
        preview = str(payload.get("bodyPreview", "") or "")
        return preview, "OK", len(preview.encode("utf-8", errors="ignore")), 0.01

    client, _, err = connect_imap(account)
    if client is None:
        return "", err, 0, 0.0
    use_uid = source == "imap_uid"

    def _imap_fetch(query_spec: str):
        if use_uid:
            return client.uid("fetch", msg_id, query_spec)
        return client.fetch(msg_id, query_spec)

    try:
        started = time.perf_counter()
        try:
            typ, _ = client.select(f'"{folder}"', readonly=True)
        except Exception:
            typ, _ = client.select('"INBOX"', readonly=True)
        if typ != "OK":
            return "", f"无法选择文件夹: {folder}", 0, 0.0

        size_typ, size_data = _imap_fetch("(RFC822.SIZE)")
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
                fetch_typ, fetch_data = _imap_fetch(f"(BODY.PEEK[]<{downloaded}.{chunk_size}>)")
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
            fetch_typ, fetch_data = _imap_fetch("(BODY.PEEK[])")
            if fetch_typ != "OK" or not fetch_data:
                return "", "读取邮件正文失败", 0, 0.0
            for item in fetch_data:
                if isinstance(item, tuple) and isinstance(item[1], bytes):
                    raw_bytes += item[1]

        if not raw_bytes:
            return "", "邮件正文为空", 0, 0.0
        msg = email.message_from_bytes(raw_bytes)
        if attachments_out is not None:
            attachments_out[:] = extract_message_attachments(msg, include_content=False)
        duration = max(0.001, time.perf_counter() - started)
        if mode == "html":
            body = extract_body_html(msg)
            if body:
                return _sanitize_mail_html(body), "OK", len(raw_bytes), duration
            return f"<pre>{html.escape(extract_body_text(msg))}</pre>", "OK", len(raw_bytes), duration
        return extract_body_text(msg), "OK", len(raw_bytes), duration
    except Exception as exc:
        return "", str(exc), 0, 0.0
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _fetch_imap_raw_bytes(account: MailAccount, item: MailItem) -> tuple[Optional[bytes], str]:
    client, _, err = connect_imap(account)
    if client is None:
        return None, err
    use_uid = item.source == "imap_uid"
    try:
        try:
            typ, _ = client.select(f'"{item.folder}"', readonly=True)
        except Exception:
            typ, _ = client.select('"INBOX"', readonly=True)
        if typ != "OK":
            return None, f"无法选择文件夹: {item.folder}"
        fetch_typ, fetch_data = (
            client.uid("fetch", item.msg_id, "(BODY.PEEK[])")
            if use_uid
            else client.fetch(item.msg_id, "(BODY.PEEK[])")
        )
        if fetch_typ != "OK" or not fetch_data:
            return None, "拉取原始邮件失败"
        raw_bytes = b""
        for part in fetch_data:
            if isinstance(part, tuple) and isinstance(part[1], bytes):
                raw_bytes += part[1]
        if not raw_bytes:
            return None, "邮件内容为空"
        return raw_bytes, "OK"
    except Exception as exc:
        return None, str(exc)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def fetch_mail_attachments_metadata(account: MailAccount, item: MailItem) -> list[dict[str, Any]]:
    if item.source == "graph":
        remote_id = item.msg_id.decode(errors="ignore")
        return fetch_graph_attachments(account, remote_id)
    raw_bytes, status = _fetch_imap_raw_bytes(account, item)
    if not raw_bytes or status != "OK":
        return []
    msg = email.message_from_bytes(raw_bytes)
    return extract_message_attachments(msg, include_content=False)


def download_mail_attachment(
    account: MailAccount,
    item: MailItem,
    attachment_id: str,
) -> tuple[Optional[bytes], str, str, str]:
    if item.source == "graph":
        remote_id = item.msg_id.decode(errors="ignore")
        return download_graph_attachment(account, remote_id, attachment_id)
    raw_bytes, status = _fetch_imap_raw_bytes(account, item)
    if not raw_bytes or status != "OK":
        return None, "", "", status
    msg = email.message_from_bytes(raw_bytes)
    for att in extract_message_attachments(msg, include_content=True):
        if att.get("id") == attachment_id:
            return (
                att.get("content", b""),
                str(att.get("name", "attachment") or "attachment"),
                str(att.get("content_type", "application/octet-stream") or "application/octet-stream"),
                "OK",
            )
    return None, "", "", "未找到指定附件"


def download_all_mail_attachments(
    account: MailAccount,
    item: MailItem,
) -> tuple[list[tuple[str, bytes]], str]:
    if item.source == "graph":
        remote_id = item.msg_id.decode(errors="ignore")
        att_list = item.attachments or fetch_graph_attachments(account, remote_id)
        if not att_list:
            return [], "该邮件没有可下载的附件"
        downloaded: list[tuple[str, bytes]] = []
        for att in att_list:
            att_id = str(att.get("id", "") or "")
            if not att_id:
                continue
            content, filename, _, status = download_graph_attachment(account, remote_id, att_id)
            if content is not None and status == "OK":
                downloaded.append((filename or str(att.get("name", "attachment")), content))
        if not downloaded:
            return [], "附件下载失败"
        return downloaded, "OK"

    raw_bytes, status = _fetch_imap_raw_bytes(account, item)
    if not raw_bytes or status != "OK":
        return [], status
    msg = email.message_from_bytes(raw_bytes)
    atts = extract_message_attachments(msg, include_content=True)
    if not atts:
        return [], "该邮件没有可下载的附件"
    return [(str(att.get("name", "attachment") or "attachment"), att.get("content", b"")) for att in atts], "OK"


def delete_mails_remote(
    account: MailAccount,
    items: list[MailItem],
) -> tuple[list[str], list[dict[str, str]]]:
    deleted_keys: list[str] = []
    errors: list[dict[str, str]] = []
    graph_items = [item for item in items if item.source == "graph"]
    imap_items = [item for item in items if item.source != "graph"]

    if graph_items:
        access_token, token_err = get_graph_access_token(account, required_scope=GRAPH_READWRITE_SCOPE)
        if not access_token:
            for item in graph_items:
                errors.append({"local_key": item.local_key, "error": token_err})
        else:
            for item in graph_items:
                remote_id = item.msg_id.decode(errors="ignore")
                _, status_code, _, req_err = _graph_api_request(
                    f"/me/messages/{quote(remote_id)}",
                    access_token,
                    method="DELETE",
                    timeout=20,
                )
                if status_code in {200, 202, 204, 404}:
                    deleted_keys.append(item.local_key)
                else:
                    msg = req_err
                    if status_code in {401, 403}:
                        msg = "Graph 删除权限不足（需要 Mail.ReadWrite），请重新完成 Graph 授权"
                    errors.append({"local_key": item.local_key, "error": msg})

    if imap_items:
        client, _, err = connect_imap(account)
        if client is None:
            for item in imap_items:
                errors.append({"local_key": item.local_key, "error": err})
        else:
            try:
                by_folder: dict[str, list[MailItem]] = {}
                for item in imap_items:
                    by_folder.setdefault(item.folder or "INBOX", []).append(item)
                for folder, folder_items in by_folder.items():
                    try:
                        typ, _ = client.select(f'"{folder}"', readonly=False)
                        if typ != "OK":
                            raise RuntimeError(f"无法打开文件夹 {folder}")
                    except Exception as exc:
                        for item in folder_items:
                            errors.append({"local_key": item.local_key, "error": str(exc)})
                        continue
                    uid_items = [it for it in folder_items if it.source == "imap_uid"]
                    seq_items = [it for it in folder_items if it.source != "imap_uid"]
                    if uid_items:
                        uid_set = b",".join(it.msg_id for it in uid_items)
                        st_typ, _ = client.uid("store", uid_set, "+FLAGS", r"(\Deleted)")
                        if st_typ == "OK":
                            deleted_keys.extend(it.local_key for it in uid_items)
                        else:
                            for it in uid_items:
                                errors.append({"local_key": it.local_key, "error": "IMAP 标记删除失败"})
                    for it in seq_items:
                        st_typ, _ = client.store(it.msg_id, "+FLAGS", r"(\Deleted)")
                        if st_typ == "OK":
                            deleted_keys.append(it.local_key)
                        else:
                            errors.append({"local_key": it.local_key, "error": "IMAP 标记删除失败"})
                    try:
                        client.expunge()
                    except Exception:
                        pass
            finally:
                try:
                    client.logout()
                except Exception:
                    pass

    return deleted_keys, errors


def mark_mails_read_remote(
    account: MailAccount,
    items: list[MailItem],
    *,
    is_read: bool = True,
) -> tuple[list[str], list[dict[str, str]]]:
    updated_keys: list[str] = []
    errors: list[dict[str, str]] = []
    graph_items = [item for item in items if item.source == "graph"]
    imap_items = [item for item in items if item.source != "graph"]

    if graph_items:
        access_token, token_err = get_graph_access_token(account, required_scope=GRAPH_READWRITE_SCOPE)
        if not access_token:
            for item in graph_items:
                errors.append({"local_key": item.local_key, "error": token_err})
        else:
            for item in graph_items:
                remote_id = item.msg_id.decode(errors="ignore")
                _, status_code, _, req_err = _graph_api_request(
                    f"/me/messages/{quote(remote_id)}",
                    access_token,
                    method="PATCH",
                    json_body={"isRead": bool(is_read)},
                    timeout=15,
                )
                if 200 <= status_code < 300:
                    updated_keys.append(item.local_key)
                else:
                    errors.append({"local_key": item.local_key, "error": req_err})

    if imap_items:
        client, _, err = connect_imap(account)
        if client is None:
            for item in imap_items:
                errors.append({"local_key": item.local_key, "error": err})
        else:
            flag_op = "+FLAGS" if is_read else "-FLAGS"
            try:
                by_folder: dict[str, list[MailItem]] = {}
                for item in imap_items:
                    by_folder.setdefault(item.folder or "INBOX", []).append(item)
                for folder, folder_items in by_folder.items():
                    try:
                        typ, _ = client.select(f'"{folder}"', readonly=False)
                        if typ != "OK":
                            raise RuntimeError(f"无法打开文件夹 {folder}")
                    except Exception as exc:
                        for item in folder_items:
                            errors.append({"local_key": item.local_key, "error": str(exc)})
                        continue
                    uid_items = [it for it in folder_items if it.source == "imap_uid"]
                    seq_items = [it for it in folder_items if it.source != "imap_uid"]
                    if uid_items:
                        uid_set = b",".join(it.msg_id for it in uid_items)
                        st_typ, _ = client.uid("store", uid_set, flag_op, r"(\Seen)")
                        if st_typ == "OK":
                            updated_keys.extend(it.local_key for it in uid_items)
                        else:
                            for it in uid_items:
                                errors.append({"local_key": it.local_key, "error": "IMAP 标记已读失败"})
                    for it in seq_items:
                        st_typ, _ = client.store(it.msg_id, flag_op, r"(\Seen)")
                        if st_typ == "OK":
                            updated_keys.append(it.local_key)
                        else:
                            errors.append({"local_key": it.local_key, "error": "IMAP 标记已读失败"})
            finally:
                try:
                    client.logout()
                except Exception:
                    pass

    return updated_keys, errors


def _normalize_email_recipients(raw_items: list[str]) -> tuple[list[str], str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in raw_items:
        for token in re.split(r"[,;\n，；]+", str(entry or "")):
            addr = token.strip()
            if not addr:
                continue
            if not EMAIL_PATTERN.fullmatch(addr):
                return [], f"邮箱地址格式无效: {addr}"
            lowered = addr.lower()
            if lowered not in seen:
                seen.add(lowered)
                normalized.append(lowered)
    return normalized, ""


def send_mail_via_graph(
    account: MailAccount,
    recipients: list[str],
    subject: str,
    body: str,
    *,
    cc: Optional[list[str]] = None,
) -> dict[str, Any]:
    if not _is_outlook_graph_candidate(account):
        return {
            "ok": False,
            "status_code": 400,
            "code": "GRAPH_SEND_UNSUPPORTED",
            "reauth_required": False,
            "message": "仅支持已配置 OAuth 凭据的 Outlook / Hotmail 账号发信",
        }
    to_list, to_err = _normalize_email_recipients(recipients)
    if to_err:
        return {"ok": False, "status_code": 400, "code": "GRAPH_SEND_INVALID_REQUEST", "reauth_required": False, "message": to_err}
    if not to_list:
        return {"ok": False, "status_code": 400, "code": "GRAPH_SEND_INVALID_REQUEST", "reauth_required": False, "message": "请至少填写一个有效收件人"}
    cc_list, cc_err = _normalize_email_recipients(cc or [])
    if cc_err:
        return {"ok": False, "status_code": 400, "code": "GRAPH_SEND_INVALID_REQUEST", "reauth_required": False, "message": cc_err}
    subject_str = str(subject or "")
    body_str = str(body or "")
    if "\r" in subject_str or "\n" in subject_str:
        return {"ok": False, "status_code": 400, "code": "GRAPH_SEND_INVALID_REQUEST", "reauth_required": False, "message": "邮件主题不能包含换行符"}
    if not subject_str.strip() and not body_str.strip():
        return {"ok": False, "status_code": 400, "code": "GRAPH_SEND_INVALID_REQUEST", "reauth_required": False, "message": "主题和正文不能同时为空"}

    access_token, token_err = get_graph_access_token(account, required_scope=GRAPH_SEND_SCOPE)
    if not access_token:
        lowered_err = token_err.lower()
        reauth = any(k in lowered_err for k in ("aadsts65001", "invalid_grant", "invalid_scope", "consent", "70000", "400", "401", "403"))
        return {
            "ok": False,
            "status_code": 403 if reauth else 400,
            "code": "GRAPH_SEND_REAUTH_REQUIRED" if reauth else "GRAPH_SEND_TOKEN_ERROR",
            "reauth_required": reauth,
            "message": "发信权限不足或授权已失效，请重新完成 Graph 授权（将包含 Mail.Send 权限）" if reauth else f"获取发信令牌失败: {token_err}",
        }

    message_payload: dict[str, Any] = {
        "subject": subject_str,
        "body": {
            "contentType": "Text",
            "content": body_str,
        },
        "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list],
    }
    if cc_list:
        message_payload["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc_list]

    # Single submission ONLY: never auto-retry sendMail on timeout/network failure to avoid duplicate emails
    _, status_code, headers, req_err = _graph_api_request(
        "/me/sendMail",
        access_token,
        method="POST",
        json_body={"message": message_payload, "saveToSentItems": True},
        timeout=30,
    )
    if status_code in {200, 202}:
        return {
            "ok": True,
            "status_code": 202,
            "submitted": True,
            "code": "OK",
            "reauth_required": False,
            "message": "邮件已提交发送",
            "to": to_list,
            "cc": cc_list,
        }
    if status_code in {401, 403}:
        return {
            "ok": False,
            "status_code": 403,
            "code": "GRAPH_SEND_REAUTH_REQUIRED",
            "reauth_required": True,
            "message": "发信权限不足（缺少 Mail.Send 权限）或授权已失效，请点击「Graph 重新授权」后再试",
        }
    if status_code == 429:
        retry_after_raw = headers.get("retry-after", "")
        retry_after = int(retry_after_raw) if retry_after_raw.isdigit() else None
        msg = f"发送请求过于频繁，请在 {retry_after} 秒后重试" if retry_after is not None else "发送请求过于频繁，请稍后重试"
        return {
            "ok": False,
            "status_code": 429,
            "code": "GRAPH_SEND_THROTTLED",
            "reauth_required": False,
            "retry_after": retry_after,
            "message": msg,
        }
    if status_code == 0 or req_err.startswith(("NETWORK_ERROR", "TIMEOUT_ERROR")):
        return {
            "ok": False,
            "status_code": 504,
            "code": "GRAPH_SEND_RESULT_UNKNOWN",
            "reauth_required": False,
            "message": "网络超时或连接中断，发送结果不确定，请先确认后再决定是否重发",
        }
    return {
        "ok": False,
        "status_code": 400,
        "code": "GRAPH_SEND_FAILED",
        "reauth_required": False,
        "message": f"邮件发送失败: {req_err}",
    }
