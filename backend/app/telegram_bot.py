from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from .imap_logic import fetch_mail_body, format_shanghai_time
from .translate import translate_text_to_chinese

if TYPE_CHECKING:
    from .manager import MailManager
    from .models import MailAccount, MailItem

DEFAULT_TELEGRAM_INSTANT_TEMPLATE = (
    "<b>📬 收到一封新邮件</b>\n"
    "━━━━━━━━━━━━━━\n"
    "<b>📁 分组：</b>{group}\n"
    "<b>📮 邮箱：</b><code>{email}</code>\n"
    "<b>📝 主题：</b>{subject}\n"
    "<b>📨 发件人：</b>{sender_email}\n"
    "<b>🕒 时间：</b>{date}\n"
    "{codes_line}\n"
    "{has_attachments}"
)

DEFAULT_TELEGRAM_SUMMARY_HEADER_TEMPLATE = (
    "<b>📬 收到 {count} 封新邮件</b>\n"
    "━━━━━━━━━━━━━━\n"
    "<b>📁 监听分组：</b>{groups}\n\n"
    "{items}\n"
    "{remaining}"
)

DEFAULT_TELEGRAM_SUMMARY_ITEM_TEMPLATE = (
    "• <code>{email}</code> | <b>{subject}</b>\n"
    "  发件人：{sender_email} {codes}"
)

DEFAULT_TELEGRAM_BUTTONS = [
    "body",
    "translate",
    "attachments",
    "star",
    "mark_read",
    "delete",
]

VALID_TELEGRAM_BUTTONS = set(DEFAULT_TELEGRAM_BUTTONS)

TELEGRAM_BUTTON_OPTIONS = [
    {"id": "body", "label": "查看正文", "description": "点击直接在 TG 中拉取并展开邮件纯文本正文（支持收起）"},
    {"id": "translate", "label": "翻译正文", "description": "调用后台配置的翻译引擎将正文翻译为中文（支持原文切换）"},
    {"id": "attachments", "label": "获取附件", "description": "当邮件包含附件时显示，点击直接发送文件/ZIP 到 TG"},
    {"id": "star", "label": "标星/取消标星", "description": "一键切换邮件星标状态并同步到 Web 端"},
    {"id": "mark_read", "label": "标记已读", "description": "一键将邮件标为已读并同步远程邮箱"},
    {"id": "delete", "label": "删除邮件", "description": "带二次确认按钮，确认后同步删除远程与本地邮件"},
]

TELEGRAM_TEMPLATE_VARIABLES = [
    {"key": "{group}", "label": "分组", "example": "重要账号"},
    {"key": "{email}", "label": "收件邮箱", "example": "user@outlook.com"},
    {"key": "{folder}", "label": "文件夹", "example": "收件箱"},
    {"key": "{subject}", "label": "邮件主题", "example": "Your verification code is 482910"},
    {"key": "{sender}", "label": "发件人全称", "example": "GitHub <noreply@github.com>"},
    {"key": "{sender_email}", "label": "发件人邮箱", "example": "noreply@github.com"},
    {"key": "{date}", "label": "邮件时间", "example": "2026-11-27 09:30:00"},
    {"key": "{codes}", "label": "验证码", "example": "482910"},
    {"key": "{codes_line}", "label": "智能验证码行", "example": "🔑 验证码：482910"},
    {"key": "{preview}", "label": "正文摘要", "example": "Hi, your one-time verification code is 482910..."},
    {"key": "{has_attachments}", "label": "附件标识", "example": "📎 含附件"},
    {"key": "{note}", "label": "账号备注", "example": "主号 / 美区"},
    {"key": "{tags}", "label": "账号标签", "example": "VIP、常用"},
]

TELEGRAM_SUMMARY_VARIABLES = [
    {"key": "{count}", "label": "本次新邮件数", "example": "3"},
    {"key": "{groups}", "label": "监听分组", "example": "全部邮箱"},
    {"key": "{items}", "label": "邮件列表块", "example": "(按单条模板渲染)"},
    {"key": "{remaining}", "label": "剩余待发提示", "example": "… 其余 2 封将继续在下一条发送"},
]

MAX_TG_MESSAGE_CHARS = 3950
MAX_TG_ATTACHMENT_BYTES = 20 * 1024 * 1024


def normalize_telegram_buttons(values: object) -> list[str]:
    if not isinstance(values, list):
        return DEFAULT_TELEGRAM_BUTTONS.copy()
    cleaned: list[str] = []
    for item in values:
        key = str(item or "").strip().lower()
        if key in VALID_TELEGRAM_BUTTONS and key not in cleaned:
            cleaned.append(key)
    return cleaned


def mail_ref_id(local_key: str) -> str:
    return hashlib.sha256(local_key.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _escape_for_mode(value: str, parse_mode: str) -> str:
    if parse_mode == "HTML":
        return html.escape(value or "", quote=False)
    return value or ""


_TG_HTML_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "blockquote", "tg-spoiler", "a",
}
_TG_TAG_TOKEN_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(\s+[^>]*)?>")


def sanitize_telegram_html(text: str) -> str:
    """Balance Telegram HTML tags: strip orphan closing tags and close unclosed opening tags."""
    if not text or "<" not in text:
        return text
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    for match in _TG_TAG_TOKEN_RE.finditer(text):
        out.append(text[pos : match.start()])
        pos = match.end()
        is_close = bool(match.group(1))
        tag = match.group(2).lower()
        attrs = match.group(3) or ""
        if tag not in _TG_HTML_TAGS:
            # Escape unknown tags so Telegram doesn't reject them
            out.append(html.escape(match.group(0), quote=False))
            continue
        if not is_close:
            if tag == "a" and attrs:
                out.append(f"<{tag}{attrs}>")
            else:
                out.append(f"<{tag}>")
            stack.append(tag)
        else:
            if tag not in stack:
                # Drop stray unmatched closing tag (e.g. orphan </b>)
                continue
            while stack:
                top = stack.pop()
                out.append(f"</{top}>")
                if top == tag:
                    break
    out.append(text[pos:])
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def render_telegram_template(
    template: str,
    context: dict[str, str],
    *,
    parse_mode: str = "HTML",
    raw_keys: Optional[set[str]] = None,
) -> str:
    mode = "HTML" if str(parse_mode or "HTML").upper() == "HTML" else "plain"
    raw_key_set = raw_keys or set()
    escaped_ctx: dict[str, str] = {}
    for key, value in context.items():
        text_val = str(value or "")
        escaped_ctx[key] = text_val if key in raw_key_set else _escape_for_mode(text_val, mode)

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in escaped_ctx:
            return escaped_ctx[var_name]
        return match.group(0)

    rendered = re.sub(r"\{([a-zA-Z0-9_]+)\}", _replace, template or "")
    # Clean trailing spaces per line and collapse excessive blank lines caused by empty optional fields
    lines = [line.rstrip() for line in rendered.splitlines()]
    collapsed: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and (prev_blank or not collapsed):
            continue
        collapsed.append(line)
        prev_blank = is_blank
    while collapsed and collapsed[-1].strip() == "":
        collapsed.pop()
    result = "\n".join(collapsed)
    if len(result) > MAX_TG_MESSAGE_CHARS:
        result = result[: MAX_TG_MESSAGE_CHARS - 12] + "\n…(内容过长已截断)"
    if mode == "HTML":
        result = sanitize_telegram_html(result)
    return result


def build_mail_template_context(
    *,
    group_name: str,
    account_email: str,
    folder: str,
    subject: str,
    sender: str,
    sender_email: str,
    date_text: str,
    codes: list[str],
    preview: str = "",
    has_attachments: bool = False,
    note: str = "",
    tags: Optional[list[str]] = None,
    parse_mode: str = "HTML",
) -> tuple[dict[str, str], set[str]]:
    mode = "HTML" if str(parse_mode or "HTML").upper() == "HTML" else "plain"
    clean_codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    codes_plain = " / ".join(clean_codes[:3])
    if mode == "HTML" and clean_codes:
        codes_formatted = " ".join(f"<code>{html.escape(c)}</code>" for c in clean_codes[:3])
        codes_line = f"<b>🔑 验证码：</b>{codes_formatted}"
    elif clean_codes:
        codes_formatted = codes_plain
        codes_line = f"🔑 验证码：{codes_plain}"
    else:
        codes_formatted = ""
        codes_line = ""

    clean_preview = re.sub(r"\s+", " ", (preview or "")).strip()[:160]
    att_text = "📎 包含附件" if has_attachments else ""
    tags_text = "、".join(t for t in (tags or []) if t)
    ctx = {
        "group": group_name or "未分组",
        "email": account_email or "-",
        "folder": folder or "收件箱",
        "subject": subject or "(无主题)",
        "sender": sender or sender_email or "-",
        "sender_email": sender_email or "-",
        "date": date_text or "-",
        "codes": codes_formatted if mode == "HTML" else codes_plain,
        "codes_line": codes_line,
        "preview": clean_preview,
        "has_attachments": att_text,
        "note": (note or "").strip(),
        "tags": tags_text,
    }
    raw_keys = {"codes", "codes_line"} if mode == "HTML" else set()
    return ctx, raw_keys


def build_mail_inline_keyboard(
    ref_id: str,
    *,
    enabled_buttons: list[str],
    expanded: bool = False,
    translated: bool = False,
    is_starred: bool = False,
    is_unread: bool = True,
    has_attachments: bool = False,
    confirm_delete: bool = False,
    is_test: bool = False,
) -> Optional[dict[str, Any]]:
    enabled = set(enabled_buttons)
    prefix = "emt" if is_test else "em"

    if confirm_delete:
        return {
            "inline_keyboard": [
                [
                    {"text": "⚠️ 确认永久删除", "callback_data": f"{prefix}:del2:{ref_id}"},
                    {"text": "取消", "callback_data": f"{prefix}:fold:{ref_id}"},
                ]
            ]
        }

    row1: list[dict[str, str]] = []
    if "body" in enabled:
        if expanded:
            row1.append({"text": "🔼 收起正文", "callback_data": f"{prefix}:fold:{ref_id}"})
        else:
            row1.append({"text": "📖 查看正文", "callback_data": f"{prefix}:body:{ref_id}"})
    if "translate" in enabled:
        if translated:
            row1.append({"text": "📄 查看原文", "callback_data": f"{prefix}:orig:{ref_id}"})
        else:
            row1.append({"text": "🌐 翻译正文", "callback_data": f"{prefix}:tr:{ref_id}"})
    if "attachments" in enabled and has_attachments:
        row1.append({"text": "📎 获取附件", "callback_data": f"{prefix}:att:{ref_id}"})

    row2: list[dict[str, str]] = []
    if "star" in enabled:
        row2.append(
            {
                "text": "★ 取消标星" if is_starred else "☆ 标星",
                "callback_data": f"{prefix}:star:{ref_id}",
            }
        )
    if "mark_read" in enabled and is_unread:
        row2.append({"text": "✅ 标为已读", "callback_data": f"{prefix}:read:{ref_id}"})
    if "delete" in enabled:
        row2.append({"text": "🗑️ 删除", "callback_data": f"{prefix}:del1:{ref_id}"})

    rows = [row for row in (row1, row2) if row]
    if not rows:
        return None
    return {"inline_keyboard": rows}


def telegram_api_call(
    bot_token: str,
    method: str,
    payload: dict[str, Any],
    *,
    timeout: int = 20,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token.strip()}/{method}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ValueError(f"Telegram HTTP {exc.code}: {err_raw[:300]}") from exc
    data = json.loads(raw)
    if not isinstance(data, dict) or not data.get("ok"):
        raise ValueError(str(data))
    return data


def telegram_send_document(
    bot_token: str,
    chat_id: str,
    filename: str,
    content: bytes,
    *,
    caption: str = "",
    timeout: int = 45,
) -> dict[str, Any]:
    boundary = f"----EasyMailTg{uuid4().hex}"
    safe_name = re.sub(r'[\r\n"\\]+', "_", filename or "attachment") or "attachment"
    mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    parts: list[bytes] = []
    fields = {"chat_id": chat_id.strip()}
    if caption:
        fields["caption"] = caption[:1000]
    for name, val in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{val}\r\n".encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{safe_name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendDocument"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        err_raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ValueError(f"Telegram sendDocument HTTP {exc.code}: {err_raw[:300]}") from exc
    data = json.loads(raw)
    if not isinstance(data, dict) or not data.get("ok"):
        raise ValueError(str(data))
    return data


class TelegramBotWorker:
    """Lightweight Telegram Bot Long Polling worker for interactive buttons & commands."""

    def __init__(self, manager: "MailManager") -> None:
        self.manager = manager
        self._stop = threading.Event()
        self._offset = 0
        self._last_bot_token = ""
        self._ref_cache: dict[str, str] = {}
        self._translated_cache: dict[str, str] = {}
        self._test_state: dict[str, dict[str, Any]] = {}

    def register_mail_ref(self, local_key: str) -> str:
        ref = mail_ref_id(local_key)
        self._ref_cache[ref] = local_key
        if len(self._ref_cache) > 5000:
            # Keep memory bounded
            keys = list(self._ref_cache.keys())[:1000]
            for k in keys:
                self._ref_cache.pop(k, None)
        return ref

    def resolve_mail_ref(self, ref_id: str) -> Optional[str]:
        if ref_id in self._ref_cache:
            return self._ref_cache[ref_id]
        with self.manager.lock:
            for local_key in self.manager.mail_items.keys():
                if mail_ref_id(local_key) == ref_id:
                    self._ref_cache[ref_id] = local_key
                    return local_key
        return None

    def start(self) -> None:
        threading.Thread(target=self._run_loop, name="telegram-bot-worker", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self.manager.lock:
                    settings = self.manager.settings
                    enabled = (
                        settings.telegram_enabled
                        and settings.telegram_interactive_enabled
                        and bool(settings.telegram_bot_token.strip())
                        and bool(settings.telegram_chat_id.strip())
                    )
                    bot_token = settings.telegram_bot_token.strip()
                    allowed_chat = settings.telegram_chat_id.strip()

                if not enabled:
                    self._stop.wait(5)
                    continue

                if bot_token != self._last_bot_token:
                    self._offset = 0
                    self._last_bot_token = bot_token

                data = telegram_api_call(
                    bot_token,
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "timeout": 25,
                        "allowed_updates": ["message", "callback_query"],
                    },
                    timeout=35,
                )
                updates = data.get("result", [])
                if isinstance(updates, list):
                    for update in updates:
                        if not isinstance(update, dict):
                            continue
                        update_id = int(update.get("update_id", 0) or 0)
                        if update_id >= self._offset:
                            self._offset = update_id + 1
                        self._handle_update(bot_token, allowed_chat, update)
            except Exception as exc:
                err_text = str(exc)
                # Back off longer on 409 Conflict (e.g. brief overlap during container recreate)
                wait_sec = 10 if "409" in err_text else 4
                self._stop.wait(wait_sec)

    def _handle_update(self, bot_token: str, allowed_chat: str, update: dict[str, Any]) -> None:
        try:
            callback = update.get("callback_query")
            if isinstance(callback, dict):
                self._handle_callback_query(bot_token, allowed_chat, callback)
                return
            message = update.get("message")
            if isinstance(message, dict):
                self._handle_command_message(bot_token, allowed_chat, message)
        except Exception as exc:
            self.manager.log_event(
                "error",
                "notification",
                "telegram_update_error",
                "telegram",
                "Telegram 更新处理异常",
                {"error": str(exc)},
            )

    def _answer_callback(
        self,
        bot_token: str,
        callback_id: str,
        text: str = "",
        *,
        show_alert: bool = False,
    ) -> None:
        try:
            payload: dict[str, Any] = {"callback_query_id": callback_id}
            if text:
                payload["text"] = text[:190]
            if show_alert:
                payload["show_alert"] = True
            telegram_api_call(bot_token, "answerCallbackQuery", payload, timeout=10)
        except Exception:
            pass

    def _edit_message(
        self,
        bot_token: str,
        chat_id: str,
        message_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> None:
        final_text = sanitize_telegram_html(text) if parse_mode == "HTML" else text
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": final_text,
            "disable_web_page_preview": True,
        }
        if parse_mode == "HTML":
            payload["parse_mode"] = "HTML"
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            telegram_api_call(bot_token, "editMessageText", payload, timeout=15)
        except ValueError as exc:
            low = str(exc).lower()
            if "message is not modified" in low:
                return
            if "can't parse entities" in low and "parse_mode" in payload:
                payload.pop("parse_mode", None)
                telegram_api_call(bot_token, "editMessageText", payload, timeout=15)
                return
            raise

    def _handle_test_callback(
        self,
        bot_token: str,
        chat_id: str,
        message_id: int,
        callback_id: str,
        action: str,
        ref_id: str,
    ) -> None:
        state = self._test_state.setdefault(
            ref_id,
            {"is_starred": False, "is_unread": True},
        )
        with self.manager.lock:
            parse_mode = self.manager.settings.telegram_parse_mode
            buttons = normalize_telegram_buttons(self.manager.settings.telegram_buttons)
        sample_body = (
            "Hello!\n\n"
            "Your EasyMail verification code is: 482910.\n"
            "This is a sample message sent by EasyMail to test your custom notification template "
            "and interactive Telegram buttons."
        )
        base_header = self.manager.render_sample_notification_text()
        mode = "HTML" if parse_mode == "HTML" else "plain"

        if action == "body" or action == "orig":
            self._answer_callback(bot_token, callback_id, "已展开示例正文")
            body_block = f"\n\n━━━━━━━━━━━━━━\n<b>📄 邮件正文：</b>\n{html.escape(sample_body)}" if mode == "HTML" else f"\n\n--------------\n邮件正文：\n{sample_body}"
            kb = build_mail_inline_keyboard(
                ref_id,
                enabled_buttons=buttons,
                expanded=True,
                translated=False,
                is_starred=state["is_starred"],
                is_unread=state["is_unread"],
                has_attachments=True,
                is_test=True,
            )
            self._edit_message(bot_token, chat_id, message_id, base_header + body_block, parse_mode=mode, reply_markup=kb)
            return

        if action == "tr":
            self._answer_callback(bot_token, callback_id, "正在翻译示例正文...")
            try:
                translated_text, provider = translate_text_to_chinese(
                    sample_body,
                    provider=self.manager.settings.translate_provider,
                    api_key=self.manager.settings.translate_api_key,
                    model=self.manager.settings.translate_model,
                    fallback_to_free=self.manager.settings.translate_fallback_to_free,
                )
            except Exception as exc:
                translated_text = f"（翻译服务调用失败：{exc}）"
                provider = "error"
            tr_block = (
                f"\n\n━━━━━━━━━━━━━━\n<b>🌐 翻译结果（{html.escape(provider)}）：</b>\n{html.escape(translated_text)}"
                if mode == "HTML"
                else f"\n\n--------------\n翻译结果（{provider}）：\n{translated_text}"
            )
            kb = build_mail_inline_keyboard(
                ref_id,
                enabled_buttons=buttons,
                expanded=True,
                translated=True,
                is_starred=state["is_starred"],
                is_unread=state["is_unread"],
                has_attachments=True,
                is_test=True,
            )
            self._edit_message(bot_token, chat_id, message_id, base_header + tr_block, parse_mode=mode, reply_markup=kb)
            return

        if action == "fold":
            self._answer_callback(bot_token, callback_id, "已收起")
            kb = build_mail_inline_keyboard(
                ref_id,
                enabled_buttons=buttons,
                expanded=False,
                translated=False,
                is_starred=state["is_starred"],
                is_unread=state["is_unread"],
                has_attachments=True,
                is_test=True,
            )
            self._edit_message(bot_token, chat_id, message_id, base_header, parse_mode=mode, reply_markup=kb)
            return

        if action == "att":
            self._answer_callback(bot_token, callback_id, "测试消息无真实附件，真实新邮件将直接发送文件到聊天", show_alert=True)
            return

        if action == "star":
            state["is_starred"] = not state["is_starred"]
            self._answer_callback(bot_token, callback_id, "已标星（演示）" if state["is_starred"] else "已取消标星（演示）")
            kb = build_mail_inline_keyboard(
                ref_id,
                enabled_buttons=buttons,
                expanded=False,
                is_starred=state["is_starred"],
                is_unread=state["is_unread"],
                has_attachments=True,
                is_test=True,
            )
            self._edit_message(bot_token, chat_id, message_id, base_header, parse_mode=mode, reply_markup=kb)
            return

        if action == "read":
            state["is_unread"] = False
            self._answer_callback(bot_token, callback_id, "已标记为已读（演示）")
            kb = build_mail_inline_keyboard(
                ref_id,
                enabled_buttons=buttons,
                expanded=False,
                is_starred=state["is_starred"],
                is_unread=False,
                has_attachments=True,
                is_test=True,
            )
            self._edit_message(bot_token, chat_id, message_id, base_header, parse_mode=mode, reply_markup=kb)
            return

        if action == "del1":
            self._answer_callback(bot_token, callback_id, "请确认是否删除")
            kb = build_mail_inline_keyboard(ref_id, enabled_buttons=buttons, confirm_delete=True, is_test=True)
            self._edit_message(bot_token, chat_id, message_id, base_header, parse_mode=mode, reply_markup=kb)
            return

        if action == "del2":
            self._answer_callback(bot_token, callback_id, "演示消息已模拟删除")
            self._edit_message(bot_token, chat_id, message_id, "🗑️ 测试通知已模拟删除（未影响真实邮件）。", parse_mode="plain")

    def _ensure_mail_body(self, local_key: str) -> tuple[Optional["MailAccount"], Optional["MailItem"], str]:
        with self.manager.lock:
            item = self.manager.mail_items.get(local_key)
            if not item:
                return None, None, "邮件不存在或已被删除"
            account = self.manager.find_account(item.account_email)
            if not account:
                return None, None, "所属邮箱账号不存在"
            if item.body_text:
                return account, item, "OK"
            msg_id = item.msg_id
            folder = item.folder
            source = item.source
            old_token = account.token

        attachments_out: list[dict] = []
        body, status, _, _ = fetch_mail_body(
            account,
            msg_id,
            folder,
            source,
            mode="text",
            attachments_out=attachments_out,
        )
        with self.manager.lock:
            live_item = self.manager.mail_items.get(local_key)
            if not live_item:
                return None, None, "邮件不存在或已被删除"
            if status == "OK":
                live_item.body_text = body
                if attachments_out:
                    live_item.attachments = attachments_out
                    live_item.has_attachments = True
                self.manager.refresh_verification_codes(live_item)
                self.manager.storage.upsert_mail_item(account.email, live_item)
            if account.token != old_token:
                self.manager._save_accounts_state()
            return account, live_item, status

    def _handle_callback_query(self, bot_token: str, allowed_chat: str, callback: dict[str, Any]) -> None:
        callback_id = str(callback.get("id", "") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", "") or "")
        message_id = int(message.get("message_id", 0) or 0)
        data = str(callback.get("data", "") or "")

        if not chat_id or chat_id != allowed_chat:
            self._answer_callback(bot_token, callback_id, "无权限操作此机器人", show_alert=True)
            return

        parts = data.split(":")
        if len(parts) != 3 or parts[0] not in {"em", "emt"}:
            self._answer_callback(bot_token, callback_id)
            return

        prefix, action, ref_id = parts
        if prefix == "emt":
            try:
                self._handle_test_callback(bot_token, chat_id, message_id, callback_id, action, ref_id)
            except Exception as exc:
                self.manager.log_event(
                    "error",
                    "notification",
                    "telegram_test_callback_error",
                    ref_id,
                    "Telegram 测试按钮回调异常",
                    {"action": action, "error": str(exc)},
                )
                self._answer_callback(bot_token, callback_id, f"操作失败：{str(exc)[:120]}", show_alert=True)
            return

        local_key = self.resolve_mail_ref(ref_id)
        if not local_key:
            self._answer_callback(bot_token, callback_id, "该邮件已不存在或缓存已清理", show_alert=True)
            return

        with self.manager.lock:
            item = self.manager.mail_items.get(local_key)
            account = self.manager.find_account(item.account_email) if item else None
            parse_mode = "HTML" if self.manager.settings.telegram_parse_mode == "HTML" else "plain"
            buttons = normalize_telegram_buttons(self.manager.settings.telegram_buttons)
            body_max_chars = max(400, min(3200, int(self.manager.settings.telegram_body_max_chars or 1800)))

        if not item or not account:
            self._answer_callback(bot_token, callback_id, "邮件或账号已不存在", show_alert=True)
            return

        try:
            if action in {"body", "orig"}:
                self._answer_callback(bot_token, callback_id, "正在加载正文...")
                account, item, status = self._ensure_mail_body(local_key)
                if not item or not account or status != "OK":
                    self._answer_callback(bot_token, callback_id, f"正文加载失败：{status}", show_alert=True)
                    return
                header_text = self.manager.render_instant_mail_notification(account, item)
                body_raw = (item.body_text or "(正文为空)").strip()
                if len(body_raw) > body_max_chars:
                    body_raw = body_raw[:body_max_chars] + "\n…(正文较长，请在 Web 端查看完整内容)"
                sep = (
                    f"\n\n━━━━━━━━━━━━━━\n<b>📄 邮件正文：</b>\n{html.escape(body_raw)}"
                    if parse_mode == "HTML"
                    else f"\n\n--------------\n邮件正文：\n{body_raw}"
                )
                full_text = header_text + sep
                if len(full_text) > MAX_TG_MESSAGE_CHARS:
                    full_text = full_text[: MAX_TG_MESSAGE_CHARS - 12] + "\n…(已截断)"
                kb = build_mail_inline_keyboard(
                    ref_id,
                    enabled_buttons=buttons,
                    expanded=True,
                    translated=False,
                    is_starred=item.is_starred,
                    is_unread=item.is_unread,
                    has_attachments=bool(item.has_attachments or item.attachments),
                )
                self._edit_message(bot_token, chat_id, message_id, full_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "tr":
                self._answer_callback(bot_token, callback_id, "正在翻译正文...")
                account, item, status = self._ensure_mail_body(local_key)
                if not item or not account or status != "OK":
                    self._answer_callback(bot_token, callback_id, f"正文加载失败：{status}", show_alert=True)
                    return
                cached_tr = self._translated_cache.get(local_key)
                if cached_tr is None:
                    with self.manager.lock:
                        tr_provider = self.manager.settings.translate_provider
                        tr_key = self.manager.settings.translate_api_key
                        tr_model = self.manager.settings.translate_model
                        tr_fallback = self.manager.settings.translate_fallback_to_free
                    source_text = (item.body_text or "").strip()[:3000]
                    if not source_text:
                        cached_tr = "(正文为空)"
                    else:
                        translated_text, used_provider = translate_text_to_chinese(
                            source_text,
                            provider=tr_provider,
                            api_key=tr_key,
                            model=tr_model,
                            fallback_to_free=tr_fallback,
                        )
                        cached_tr = f"[{used_provider}]\n{translated_text}"
                        self._translated_cache[local_key] = cached_tr
                        if len(self._translated_cache) > 500:
                            for k in list(self._translated_cache.keys())[:100]:
                                self._translated_cache.pop(k, None)
                header_text = self.manager.render_instant_mail_notification(account, item)
                tr_display = cached_tr
                if len(tr_display) > body_max_chars:
                    tr_display = tr_display[:body_max_chars] + "\n…(译文较长已截断)"
                sep = (
                    f"\n\n━━━━━━━━━━━━━━\n<b>🌐 中文翻译：</b>\n{html.escape(tr_display)}"
                    if parse_mode == "HTML"
                    else f"\n\n--------------\n中文翻译：\n{tr_display}"
                )
                full_text = header_text + sep
                if len(full_text) > MAX_TG_MESSAGE_CHARS:
                    full_text = full_text[: MAX_TG_MESSAGE_CHARS - 12] + "\n…(已截断)"
                kb = build_mail_inline_keyboard(
                    ref_id,
                    enabled_buttons=buttons,
                    expanded=True,
                    translated=True,
                    is_starred=item.is_starred,
                    is_unread=item.is_unread,
                    has_attachments=bool(item.has_attachments or item.attachments),
                )
                self._edit_message(bot_token, chat_id, message_id, full_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "fold":
                self._answer_callback(bot_token, callback_id, "已收起")
                header_text = self.manager.render_instant_mail_notification(account, item)
                kb = build_mail_inline_keyboard(
                    ref_id,
                    enabled_buttons=buttons,
                    expanded=False,
                    translated=False,
                    is_starred=item.is_starred,
                    is_unread=item.is_unread,
                    has_attachments=bool(item.has_attachments or item.attachments),
                )
                self._edit_message(bot_token, chat_id, message_id, header_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "att":
                self._answer_callback(bot_token, callback_id, "正在获取附件并发送到聊天...")
                try:
                    zip_bytes, zip_name = self.manager.download_all_attachments_zip(local_key)
                except Exception as exc:
                    self._answer_callback(bot_token, callback_id, f"附件获取失败：{exc}", show_alert=True)
                    return
                if len(zip_bytes) > MAX_TG_ATTACHMENT_BYTES:
                    telegram_api_call(
                        bot_token,
                        "sendMessage",
                        {
                            "chat_id": chat_id,
                            "text": f"⚠️ 附件包体积超过 20MB（{len(zip_bytes) / (1024*1024):.1f} MB），请前往 EasyMail Web 端下载。",
                        },
                    )
                    return
                telegram_send_document(
                    bot_token,
                    chat_id,
                    zip_name,
                    zip_bytes,
                    caption=f"📎 邮件附件：{item.subject[:80]}（{account.email}）",
                )
                return

            if action == "star":
                new_star = self.manager.toggle_mail_star(local_key)
                self._answer_callback(bot_token, callback_id, "已标星 ⭐" if new_star else "已取消标星")
                header_text = self.manager.render_instant_mail_notification(account, item)
                kb = build_mail_inline_keyboard(
                    ref_id,
                    enabled_buttons=buttons,
                    expanded=False,
                    is_starred=new_star,
                    is_unread=item.is_unread,
                    has_attachments=bool(item.has_attachments or item.attachments),
                )
                self._edit_message(bot_token, chat_id, message_id, header_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "read":
                self.manager.mark_mails_read([local_key], is_read=True)
                self._answer_callback(bot_token, callback_id, "已标为已读 ✅")
                header_text = self.manager.render_instant_mail_notification(account, item)
                kb = build_mail_inline_keyboard(
                    ref_id,
                    enabled_buttons=buttons,
                    expanded=False,
                    is_starred=item.is_starred,
                    is_unread=False,
                    has_attachments=bool(item.has_attachments or item.attachments),
                )
                self._edit_message(bot_token, chat_id, message_id, header_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "del1":
                self._answer_callback(bot_token, callback_id, "请再次确认删除")
                header_text = self.manager.render_instant_mail_notification(account, item)
                kb = build_mail_inline_keyboard(ref_id, enabled_buttons=buttons, confirm_delete=True)
                self._edit_message(bot_token, chat_id, message_id, header_text, parse_mode=parse_mode, reply_markup=kb)
                return

            if action == "del2":
                self._answer_callback(bot_token, callback_id, "正在删除邮件...")
                res = self.manager.delete_mails([local_key])
                if res.get("deleted_count", 0) > 0:
                    self._edit_message(
                        bot_token,
                        chat_id,
                        message_id,
                        f"🗑️ 邮件已永久删除：{item.subject}\n（{account.email}）",
                        parse_mode="plain",
                    )
                else:
                    err = (res.get("errors") or [{}])[0].get("error", "删除失败")
                    telegram_api_call(
                        bot_token,
                        "sendMessage",
                        {"chat_id": chat_id, "text": f"❌ 删除失败：{err}"},
                    )
                return
        except Exception as exc:
            self.manager.log_event(
                "error",
                "notification",
                "telegram_callback_error",
                local_key,
                "Telegram 交互回调异常",
                {"action": action, "error": str(exc)},
            )
            self._answer_callback(bot_token, callback_id, f"操作失败：{str(exc)[:120]}", show_alert=True)

    def _handle_command_message(self, bot_token: str, allowed_chat: str, message: dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", "") or "")
        if not chat_id or chat_id != allowed_chat:
            return
        text = str(message.get("text", "") or "").strip()
        if not text.startswith("/"):
            return
        parts = text.split(None, 1)
        cmd = parts[0].split("@", 1)[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in {"/help", "/start"}:
            help_text = (
                "<b>🤖 EasyMail Bot 快捷指令</b>\n"
                "━━━━━━━━━━━━━━\n"
                "• <code>/status</code> — 查看邮箱总数、成功/失败与队列状态\n"
                "• <code>/latest</code> — 查看最近 5 封邮件（带快捷操作按钮）\n"
                "• <code>/receive 邮箱地址</code> — 立即触发指定邮箱收件\n"
                "• <code>/receive all</code> — 触发全部邮箱收件\n"
                "• <code>/help</code> — 显示此帮助信息"
            )
            telegram_api_call(
                bot_token,
                "sendMessage",
                {"chat_id": chat_id, "text": help_text, "parse_mode": "HTML"},
            )
            return

        if cmd == "/status":
            with self.manager.lock:
                total = len(self.manager.accounts)
                success = sum(1 for a in self.manager.accounts if a.status == "登录成功")
                failed = sum(1 for a in self.manager.accounts if a.status in {"登录失败", "收信失败"})
                unread = sum(a.unseen_count for a in self.manager.accounts)
                busy = self.manager.receive_busy_email or "空闲"
            msg = (
                "<b>📊 EasyMail 运行状态</b>\n"
                "━━━━━━━━━━━━━━\n"
                f"• 邮箱总数：<b>{total}</b>（成功 {success} / 失败 {failed}）\n"
                f"• 未读邮件：<b>{unread}</b> 封\n"
                f"• 收件队列：{html.escape(busy)}\n"
                f"• 时间：{format_shanghai_time(self.manager._now_shanghai())}"
            )
            telegram_api_call(
                bot_token,
                "sendMessage",
                {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            )
            return

        if cmd == "/latest":
            with self.manager.lock:
                recent = list(self.manager.all_mails[:5])
                buttons = normalize_telegram_buttons(self.manager.settings.telegram_buttons)
                parse_mode = "HTML" if self.manager.settings.telegram_parse_mode == "HTML" else "plain"
            if not recent:
                telegram_api_call(bot_token, "sendMessage", {"chat_id": chat_id, "text": "📭 当前暂无缓存邮件。"})
                return
            for mail in recent:
                with self.manager.lock:
                    account = self.manager.find_account(mail.account_email)
                if not account:
                    continue
                ref = self.register_mail_ref(mail.local_key)
                text_out = self.manager.render_instant_mail_notification(account, mail)
                kb = build_mail_inline_keyboard(
                    ref,
                    enabled_buttons=buttons,
                    expanded=False,
                    is_starred=mail.is_starred,
                    is_unread=mail.is_unread,
                    has_attachments=bool(mail.has_attachments or mail.attachments),
                )
                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": text_out,
                    "disable_web_page_preview": True,
                }
                if parse_mode == "HTML":
                    payload["parse_mode"] = "HTML"
                if kb:
                    payload["reply_markup"] = kb
                telegram_api_call(bot_token, "sendMessage", payload)
            return

        if cmd == "/receive":
            if not arg:
                telegram_api_call(
                    bot_token,
                    "sendMessage",
                    {"chat_id": chat_id, "text": "用法：/receive 邮箱地址  或  /receive all"},
                )
                return
            if arg.lower() == "all":
                with self.manager.lock:
                    targets = list(self.manager.accounts)
                    self.manager.start_receive_batch(targets, priority=20, interrupt_pending=False)
                telegram_api_call(
                    bot_token,
                    "sendMessage",
                    {"chat_id": chat_id, "text": f"📥 已将全部 {len(targets)} 个邮箱加入收件队列。"},
                )
                return
            with self.manager.lock:
                target = self.manager.find_account(arg)
            if not target:
                telegram_api_call(
                    bot_token,
                    "sendMessage",
                    {"chat_id": chat_id, "text": f"❌ 未找到邮箱：{arg}"},
                )
                return
            self.manager.start_receive_batch([target], priority=10, interrupt_pending=False)
            telegram_api_call(
                bot_token,
                "sendMessage",
                {"chat_id": chat_id, "text": f"📥 已触发收件：{target.email}"},
            )
