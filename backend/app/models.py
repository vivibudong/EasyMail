from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Optional

IMAP_HOST = "imap-mail.outlook.com"
IMAP_PORT = 993


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
    flag_color: str = ""
    group_name: str = "未分组"
    tags: list[str] = field(default_factory=list)


@dataclass
class GroupDefinition:
    name: str
    color: str = "#D6EAF8"
    priority: int = 100


@dataclass
class TagDefinition:
    name: str
    color: str = "#BFDBFE"
    priority: int = 100


@dataclass
class AppSettings:
    auto_receive_interval: int = 120
    txt_delimiter_preset: str = "auto"
    txt_delimiter_regex: str = r"\s*(?:-{3,}|\|\||\||,|;|\t)\s*"
    import_delimiters: list[str] = field(
        default_factory=lambda: [r"-{3,}", r"\|\|", r"\|", r",", r";", r"\t"]
    )
    txt_comment_prefix: str = "#"
    txt_skip_first_line: bool = False
    startup_auto_login: bool = True
    mail_list_limit: int = 0
    mark_read_on_open: bool = True
    custom_groups: list[GroupDefinition] = field(default_factory=list)
    custom_tags: list[TagDefinition] = field(default_factory=list)
    auto_receive_enabled: bool = False
    auto_receive_interval_minutes: int = 15
    token_refresh_enabled: bool = False
    token_refresh_interval_minutes: int = 360
    backup_enabled: bool = False
    backup_interval_minutes: int = 1440
    backup_directory: str = "backups"
    backup_keep_count: int = 10


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
        )
    except Exception:
        return None


def account_to_dict(a: MailAccount) -> dict:
    return {
        "email": a.email,
        "password": a.password,
        "auth_code_or_client_id": a.auth_code_or_client_id,
        "token": a.token,
        "imap_host": a.imap_host,
        "imap_port": a.imap_port,
        "cached_access_token": a.cached_access_token,
        "cached_access_expire_at": a.cached_access_expire_at,
        "cached_graph_access_token": a.cached_graph_access_token,
        "cached_graph_access_expire_at": a.cached_graph_access_expire_at,
        "flag_color": a.flag_color,
        "group_name": a.group_name,
        "tags": a.tags,
    }


def account_from_dict(data: dict) -> Optional[MailAccount]:
    email_addr = str(data.get("email", "")).strip()
    if not email_addr or "@" not in email_addr:
        return None
    try:
        port = int(data.get("imap_port", IMAP_PORT))
    except Exception:
        port = IMAP_PORT
    return MailAccount(
        email=email_addr,
        password=str(data.get("password", "")),
        auth_code_or_client_id=str(data.get("auth_code_or_client_id", "")),
        token=str(data.get("token", "")),
        imap_host=str(data.get("imap_host", IMAP_HOST)),
        imap_port=port,
        status="待登录",
        cached_access_token=str(data.get("cached_access_token", "")),
        cached_access_expire_at=float(data.get("cached_access_expire_at", 0.0) or 0.0),
        cached_graph_access_token=str(data.get("cached_graph_access_token", "")),
        cached_graph_access_expire_at=float(data.get("cached_graph_access_expire_at", 0.0) or 0.0),
        flag_color=str(data.get("flag_color", "")),
        group_name=str(data.get("group_name", "未分组") or "未分组"),
        tags=[str(item) for item in data.get("tags", []) if str(item).strip()],
    )


def settings_to_dict(settings: AppSettings) -> dict:
    return {
        "auto_receive_interval": settings.auto_receive_interval,
        "txt_delimiter_preset": settings.txt_delimiter_preset,
        "txt_delimiter_regex": settings.txt_delimiter_regex,
        "import_delimiters": settings.import_delimiters,
        "txt_comment_prefix": settings.txt_comment_prefix,
        "txt_skip_first_line": settings.txt_skip_first_line,
        "startup_auto_login": settings.startup_auto_login,
        "mail_list_limit": settings.mail_list_limit,
        "mark_read_on_open": settings.mark_read_on_open,
        "custom_groups": [
            {"name": item.name, "color": item.color, "priority": item.priority}
            for item in settings.custom_groups
        ],
        "custom_tags": [
            {"name": item.name, "color": item.color, "priority": item.priority}
            for item in settings.custom_tags
        ],
        "auto_receive_enabled": settings.auto_receive_enabled,
        "auto_receive_interval_minutes": settings.auto_receive_interval_minutes,
        "token_refresh_enabled": settings.token_refresh_enabled,
        "token_refresh_interval_minutes": settings.token_refresh_interval_minutes,
        "backup_enabled": settings.backup_enabled,
        "backup_interval_minutes": settings.backup_interval_minutes,
        "backup_directory": settings.backup_directory,
        "backup_keep_count": settings.backup_keep_count,
    }


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

    return AppSettings(
        auto_receive_interval=int(data.get("auto_receive_interval", 120) or 120),
        txt_delimiter_preset=str(data.get("txt_delimiter_preset", "auto")),
        txt_delimiter_regex=str(data.get("txt_delimiter_regex", r"\s*(?:-{3,}|\|\||\||,|;|\t)\s*")),
        import_delimiters=[
            str(item).strip()
            for item in data.get("import_delimiters", [r"-{3,}", r"\|\|", r"\|", r",", r";", r"\t"])
            if str(item).strip()
        ],
        txt_comment_prefix=str(data.get("txt_comment_prefix", "#")),
        txt_skip_first_line=bool(data.get("txt_skip_first_line", False)),
        startup_auto_login=bool(data.get("startup_auto_login", True)),
        mail_list_limit=int(data.get("mail_list_limit", 0) or 0),
        mark_read_on_open=bool(data.get("mark_read_on_open", True)),
        custom_groups=group_items,
        custom_tags=tag_items,
        auto_receive_enabled=bool(data.get("auto_receive_enabled", False)),
        auto_receive_interval_minutes=int(data.get("auto_receive_interval_minutes", 15) or 15),
        token_refresh_enabled=bool(data.get("token_refresh_enabled", False)),
        token_refresh_interval_minutes=int(data.get("token_refresh_interval_minutes", 360) or 360),
        backup_enabled=bool(data.get("backup_enabled", False)),
        backup_interval_minutes=int(data.get("backup_interval_minutes", 1440) or 1440),
        backup_directory=str(data.get("backup_directory", "backups") or "backups"),
        backup_keep_count=int(data.get("backup_keep_count", 10) or 10),
    )
