from __future__ import annotations

import json
import base64
import hashlib
import os
import re
import secrets
import subprocess
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import create_access_token, get_current_user, security
from .config import config, update_admin_credentials
from .manager import MailManager
from .models import DEFAULT_IMPORT_DELIMITERS, MailAccount
from .storage import SqliteStorage

GRAPH_REAUTH_SCOPE = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
MANUAL_OAUTH_SCOPE = GRAPH_REAUTH_SCOPE
MICROSOFT_CONSUMERS_BASE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
PROJECT_REPO = "vivibudong/EasyMail"
PROJECT_RELEASES_URL = f"https://github.com/{PROJECT_REPO}/releases"
API_SCOPES = {
    "read:accounts",
    "read:mails",
    "write:accounts",
    "write:taxonomy",
    "task:receive",
    "task:login",
    "task:backup",
    "notify:send",
    "read:logs",
    "admin:tokens",
}

storage = SqliteStorage(config.data_dir)
manager = MailManager(storage)
version_cache: dict[str, object] = {"expires_at": 0.0, "payload": None}

if config.generated_credentials:
    print("EasyMail initial admin credentials", flush=True)
    print(f"ADMIN_EMAIL={config.generated_credentials['admin_email']}", flush=True)
    print(f"ADMIN_PASSWORD={config.generated_credentials['admin_password']}", flush=True)

app = FastAPI(title=config.app_name, description=config.app_description)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class GraphReauthSession:
    session_id: str
    email: str
    client_id: str
    device_code: str
    user_code: str
    verification_uri: str
    expires_at: float
    interval: int
    status: str = "pending"
    message: str = ""
    next_poll_at: float = 0.0


graph_reauth_sessions: dict[str, GraphReauthSession] = {}
manual_oauth_sessions: dict[str, dict] = {}


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminCredentialsRequest(BaseModel):
    email: str
    current_password: str
    new_password: str


class AccountBatchRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    include_all: bool = False


class FlagRequest(BaseModel):
    email: str
    flag_color: str = ""


class GroupRequest(BaseModel):
    name: str
    color: str = "#D6EAF8"
    priority: int = 100


class GroupUpdateRequest(BaseModel):
    original_name: str
    name: str
    color: str = "#D6EAF8"
    priority: int = 100


class TagRequest(BaseModel):
    name: str
    color: str = "#BFDBFE"
    priority: int = 100


class TagUpdateRequest(BaseModel):
    original_name: str
    name: str
    color: str = "#BFDBFE"
    priority: int = 100


class AccountGroupRequest(BaseModel):
    email: str
    group_name: str


class AccountTagsRequest(BaseModel):
    email: str
    tags: list[str] = Field(default_factory=list)


class AccountUpdateRequest(BaseModel):
    original_email: str
    email: str
    password: str = ""
    auth_code_or_client_id: str = ""
    token: str = ""
    imap_host: str = "imap-mail.outlook.com"
    imap_port: int = 993
    group_name: str = "未分组"
    flag_color: str = ""
    tags: list[str] = Field(default_factory=list)
    note: str = ""


class GraphReauthStartRequest(BaseModel):
    email: str


class ManualOauthStartRequest(BaseModel):
    email: str
    password: str = ""


class ManualOauthCompleteRequest(BaseModel):
    session_id: str
    callback_url: str


class MailOpenRequest(BaseModel):
    local_key: str


class MailStarRequest(BaseModel):
    local_key: str
    is_starred: Optional[bool] = None


class TranslateRequest(BaseModel):
    text: str


class ApiTokenCreateRequest(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)


class ApiGroupRequest(BaseModel):
    name: str
    color: str = "#D6EAF8"
    priority: int = 100


class ApiTagRequest(BaseModel):
    name: str
    color: str = "#BFDBFE"
    priority: int = 100


class ApiAccountGroupRequest(BaseModel):
    group_name: str


class ApiBatchGroupRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    group_name: str


class ApiTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class ApiBatchTagsRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ApiFlagRequest(BaseModel):
    flag_color: str = ""


class ApiBatchFlagRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    flag_color: str = ""


class ApiAccountImportRequest(BaseModel):
    mode: str = "text"
    content: str


class ApiTaskTargetRequest(BaseModel):
    emails: list[str] = Field(default_factory=list)
    include_all: bool = False
    group_name: str = ""
    tag_name: str = ""


class ApiBackupRequest(BaseModel):
    include_accounts: bool = True
    include_settings: bool = True
    include_taxonomy: bool = True
    include_logs: bool = False


class ApiNotificationRequest(BaseModel):
    title: str = "手动通知"
    content: str


class SettingsRequest(BaseModel):
    auto_receive_interval: int = 120
    import_delimiters: list[str] = Field(default_factory=lambda: DEFAULT_IMPORT_DELIMITERS.copy())
    txt_comment_prefix: str = "#"
    txt_skip_first_line: bool = False
    startup_auto_login: bool = True
    mail_list_limit: int = 0
    mark_read_on_open: bool = True
    custom_groups: list[dict] = Field(default_factory=list)
    custom_tags: list[dict] = Field(default_factory=list)
    auto_receive_enabled: bool = False
    auto_receive_interval_minutes: int = 15
    token_refresh_enabled: bool = False
    token_refresh_interval_minutes: int = 360
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
    telegram_mail_groups: list[str] = Field(default_factory=list)
    telegram_mail_summary_minutes: int = 60
    telegram_notify_backup: bool = False


def ok(message: str, data: Optional[dict] = None) -> dict:
    return {"success": True, "message": message, "data": data or {}}


def api_ok(message: str = "ok", data: Optional[dict] = None, request_id: str = "") -> dict:
    return {
        "success": True,
        "message": message,
        "data": data or {},
        "request_id": request_id or f"req_{uuid4().hex}",
    }


def _hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_scopes(scopes: list[str]) -> list[str]:
    cleaned = []
    for item in scopes:
        scope = str(item).strip()
        if not scope:
            continue
        if scope not in API_SCOPES:
            raise ValueError(f"未知权限: {scope}")
        if scope not in cleaned:
            cleaned.append(scope)
    return cleaned


def _safe_account(account: MailAccount, index: int = 0) -> dict:
    return {
        **manager.serialize_account(account, index),
        "has_password": bool(account.password),
        "has_token": bool(account.token),
        "has_client_id": bool(account.auth_code_or_client_id),
    }


def _safe_mail(mail: MailItem, include_body: bool = False) -> dict:
    item = manager.serialize_mail(mail)
    if not include_body:
        item.pop("body_text", None)
        item.pop("body_html", None)
    return item


def _paginate(items: list, page: int, page_size: int) -> dict:
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"


def _api_audit(request: Request, user: dict, action: str, subject: str, detail: Optional[dict] = None) -> None:
    manager.log_event(
        "info",
        "api",
        action,
        subject,
        "API 调用",
        {
            "token_id": user.get("token_id"),
            "token_name": user.get("token_name"),
            "ip": request.client.host if request.client else "",
            **(detail or {}),
        },
    )


def require_api_scope(scope: str):
    def dependency(
        request: Request,
        credentials=Depends(security),
    ) -> dict:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="缺少 API Token")
        token = credentials.credentials.strip()
        item = storage.find_api_token_by_hash(_hash_api_token(token))
        if not item or not item.get("enabled"):
            raise HTTPException(status_code=401, detail="API Token 无效或已禁用")
        scopes = set(item.get("scopes", []))
        if scope not in scopes:
            raise HTTPException(status_code=403, detail=f"缺少权限: {scope}")
        storage.touch_api_token(str(item["id"]), request.client.host if request.client else "")
        return {
            "token_id": item["id"],
            "token_name": item["name"],
            "scopes": item["scopes"],
            "role": "api",
        }

    return dependency


def _resolve_api_targets(payload: ApiTaskTargetRequest) -> list[MailAccount]:
    with manager.lock:
        if payload.include_all:
            return manager.accounts.copy()
        if payload.group_name:
            return [
                account for account in manager.accounts
                if (account.group_name or "未分组") == payload.group_name
            ]
        if payload.tag_name:
            return [
                account for account in manager.accounts
                if payload.tag_name in account.tags
            ]
        emails = {item.strip().lower() for item in payload.emails if item.strip()}
        return [account for account in manager.accounts if account.email.lower() in emails]


def _normalize_version(value: str) -> str:
    return str(value or "").strip().lstrip("v") or "0.0.0"


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", _normalize_version(value))
    return tuple(int(part) for part in parts[:4]) or (0,)


def _fetch_latest_release() -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{PROJECT_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "EasyMail"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub 返回格式异常")
    return payload


def _version_payload(force: bool = False) -> dict:
    now = time.time()
    cached_payload = version_cache.get("payload")
    if not force and cached_payload and float(version_cache.get("expires_at", 0.0) or 0.0) > now:
        payload = dict(cached_payload)
        payload["cached"] = True
        return payload
    current_version = _normalize_version(config.app_version)
    latest_version = current_version
    release_info = {
        "name": f"v{current_version}",
        "body": "",
        "published_at": "",
        "html_url": PROJECT_RELEASES_URL,
    }
    warning = ""
    try:
        release = _fetch_latest_release()
        latest_version = _normalize_version(str(release.get("tag_name") or current_version))
        release_info = {
            "name": str(release.get("name") or f"v{latest_version}"),
            "body": str(release.get("body") or ""),
            "published_at": str(release.get("published_at") or ""),
            "html_url": str(release.get("html_url") or PROJECT_RELEASES_URL),
        }
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            warning = str(exc)
    except Exception as exc:
        warning = str(exc)
    payload = {
        "current_version": current_version,
        "latest_version": latest_version,
        "has_update": _version_tuple(latest_version) > _version_tuple(current_version),
        "release_info": release_info,
        "cached": False,
        "warning": warning,
        "build_type": os.getenv("BUILD_TYPE", "release"),
    }
    version_cache["payload"] = payload
    version_cache["expires_at"] = now + 3600
    return dict(payload)


def _run_update_command() -> dict:
    compose_file = os.getenv("EASYMAIL_COMPOSE_FILE", "")
    base_cmd = ["docker", "compose"]
    if compose_file:
        base_cmd.extend(["-f", compose_file])
    commands = [
        [*base_cmd, "pull"],
        [*base_cmd, "up", "-d"],
    ]
    outputs: list[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=os.getenv("EASYMAIL_COMPOSE_DIR", "/app"),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        outputs.append((completed.stdout or "") + (completed.stderr or ""))
        if completed.returncode != 0:
            raise RuntimeError(f"{' '.join(command)} 执行失败: {outputs[-1].strip()}")
    return {"output": "\n".join(outputs).strip()}


def _schedule_exit(delay: float = 0.8) -> None:
    def exit_later() -> None:
        time.sleep(delay)
        os._exit(0)

    threading.Thread(target=exit_later, daemon=True).start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": _normalize_version(config.app_version)}


def _validate_admin_email(email: str) -> str:
    value = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=422, detail="管理员账号必须为邮箱格式")
    return value


def _validate_admin_password(password: str) -> None:
    if len(password) <= 12:
        raise HTTPException(status_code=422, detail="密码长度必须大于 12 位")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=422, detail="密码必须包含小写字母")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=422, detail="密码必须包含大写字母")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=422, detail="密码必须包含数字")


def _post_form_json(url: str, payload: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ValueError(raw) from exc
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError(raw) from exc
    if not isinstance(data, dict):
        raise ValueError(raw)
    return data


def _serialize_graph_reauth_session(session: GraphReauthSession) -> dict:
    return {
        "session_id": session.session_id,
        "email": session.email,
        "client_id": session.client_id,
        "user_code": session.user_code,
        "verification_uri": session.verification_uri,
        "expires_in": max(0, int(session.expires_at - time.time())),
        "interval": session.interval,
        "status": session.status,
        "message": session.message,
    }


def _generate_code_verifier(length: int = 96) -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _build_authorize_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": MANUAL_OAUTH_SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "login",
        }
    )
    return f"{MICROSOFT_CONSUMERS_BASE_URL}/authorize?{query}"


def _get_graph_profile(access_token: str) -> dict:
    request = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName,displayName",
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ValueError(raw) from exc
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise ValueError(raw) from exc
    if not isinstance(payload, dict):
        raise ValueError(raw)
    return payload


def _translate_to_chinese(text: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"https://translate.googleapis.com/translate_a/single?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("翻译服务返回格式异常")
    translated_parts: list[str] = []
    for item in payload[0]:
        if isinstance(item, list) and item:
            translated_parts.append(str(item[0] or ""))
    translated_text = "".join(translated_parts).strip()
    if not translated_text:
        raise ValueError("翻译结果为空")
    return translated_text


def _apply_graph_reauth_success(session: GraphReauthSession, token_payload: dict) -> None:
    refresh_token = str(token_payload.get("refresh_token", "") or "")
    if not refresh_token:
        raise ValueError("微软返回中缺少 refresh_token")
    account = manager.find_account(session.email)
    if not account:
        raise ValueError("账号不存在，无法保存新令牌")
    with manager.lock:
        account.auth_code_or_client_id = session.client_id
        account.token = refresh_token
        account.cached_access_token = ""
        account.cached_access_expire_at = 0.0
        account.cached_graph_access_token = ""
        account.cached_graph_access_expire_at = 0.0
        account.last_error = ""
        account.status = "待登录"
        manager._save_accounts_state()
        manager.enqueue_login(account)
        manager.log_event(
            "info",
            "graph_reauth",
            "complete",
            account.email,
            "Graph 重新授权成功",
            {"client_id": session.client_id},
        )


def _poll_graph_reauth_session(session: GraphReauthSession) -> GraphReauthSession:
    if session.status != "pending":
        return session
    now = time.time()
    if now >= session.expires_at:
        session.status = "expired"
        session.message = "授权码已过期，请重新发起 Graph 重新授权"
        return session
    if now < session.next_poll_at:
        return session
    try:
        data = _post_form_json(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            {
                "client_id": session.client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": session.device_code,
            },
        )
    except ValueError as exc:
        text = str(exc)
        try:
            payload = json.loads(text)
        except Exception:
            payload = {"error_description": text}
        error_code = str(payload.get("error", "") or "")
        session.message = str(payload.get("error_description", text) or text)
        if error_code in {"authorization_pending", "slow_down"}:
            if error_code == "slow_down":
                session.interval += 5
            session.next_poll_at = now + max(1, session.interval)
            return session
        session.status = "expired" if error_code == "expired_token" else "failed"
        return session

    _apply_graph_reauth_success(session, data)
    session.status = "completed"
    session.message = "Graph 重新授权成功，已保存新令牌并重新登录"
    session.next_poll_at = now + max(1, session.interval)
    return session


def resolve_targets(payload: AccountBatchRequest) -> list:
    if payload.include_all:
        return manager.accounts.copy()
    return [manager.find_account(email_addr) for email_addr in payload.emails]


@app.get("/api/app-config")
def app_config() -> dict:
    return ok("ok", config.public_settings)


@app.get("/api/system/version")
def system_version(current_user: dict = Depends(get_current_user)) -> dict:
    return ok(
        "ok",
        {
            "current_version": _normalize_version(config.app_version),
            "build_type": os.getenv("BUILD_TYPE", "release"),
        },
    )


@app.get("/api/system/check-updates")
def check_system_updates(
    force: bool = Query(False),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return ok("ok", _version_payload(force=force))


@app.post("/api/system/update")
def update_system(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        result = _run_update_command()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail="当前运行环境未安装 Docker CLI，无法在容器内执行在线更新。请在宿主机执行 docker compose pull && docker compose up -d。",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=400, detail="在线更新超时，请在宿主机检查 Docker 状态。") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"在线更新失败: {exc}") from exc

    version_cache["payload"] = None
    version_cache["expires_at"] = 0.0
    manager.log_event("info", "system", "update", current_user["email"], "在线更新完成", result)
    return ok("更新完成，请点击立即重启", {"need_restart": True, **result})


@app.post("/api/system/restart")
def restart_system(current_user: dict = Depends(get_current_user)) -> dict:
    manager.log_event("warn", "system", "restart", current_user["email"], "管理员触发服务重启")
    _schedule_exit()
    return ok("服务正在重启", {"restarting": True})


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    if payload.email != config.admin_email or not config.verify_admin_password(payload.password):
        manager.log_event("warn", "auth", "login_denied", payload.email, "后台登录失败")
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(payload.email)
    manager.log_event("info", "auth", "login_success", payload.email, "后台登录成功")
    return ok(
        "登录成功",
        {
            "token": token,
            "user": {"email": config.admin_email, "role": "admin"},
        },
    )


@app.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user)) -> dict:
    return ok("ok", {"user": current_user})


@app.get("/api/api-tokens")
def list_api_tokens(current_user: dict = Depends(get_current_user)) -> dict:
    return ok("ok", {"items": storage.list_api_tokens(), "available_scopes": sorted(API_SCOPES)})


@app.post("/api/api-tokens")
def create_api_token(
    payload: ApiTokenCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Token 名称不能为空")
    try:
        scopes = _clean_scopes(payload.scopes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not scopes:
        raise HTTPException(status_code=400, detail="至少选择一个权限")
    raw_token = f"em_{secrets.token_urlsafe(36)}"
    token_id = uuid4().hex
    item = storage.create_api_token(token_id, name, _hash_api_token(raw_token), scopes)
    manager.log_event("info", "api_token", "create", token_id, "创建 API Token", {"name": name, "scopes": scopes})
    return ok("API Token 已创建，请立即复制保存", {"token": raw_token, "item": item})


@app.post("/api/api-tokens/{token_id}/disable")
def disable_api_token(
    token_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not storage.set_api_token_enabled(token_id, False):
        raise HTTPException(status_code=404, detail="API Token 不存在")
    manager.log_event("warn", "api_token", "disable", token_id, "禁用 API Token")
    return ok("API Token 已禁用")


@app.put("/api/auth/admin-credentials")
def update_admin_login(
    payload: AdminCredentialsRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    admin_email = _validate_admin_email(payload.email)
    _validate_admin_password(payload.new_password)
    if not config.verify_admin_password(payload.current_password):
        manager.log_event("warn", "auth", "admin_credentials_denied", current_user["email"], "安全设置修改失败")
        raise HTTPException(status_code=401, detail="当前密码错误")

    previous_email = config.admin_email
    update_admin_credentials(admin_email, payload.new_password)
    token = create_access_token(admin_email)
    manager.log_event(
        "info",
        "auth",
        "admin_credentials_updated",
        admin_email,
        "安全设置已更新",
        {"previous_email": previous_email, "new_email": admin_email},
    )
    return ok(
        "安全设置已更新",
        {
            "token": token,
            "user": {"email": admin_email, "role": "admin"},
        },
    )


@app.get("/api/dashboard/state")
def dashboard_state(
    current_user: dict = Depends(get_current_user),
) -> dict:
    return ok("ok", manager.dashboard_state())


@app.post("/api/accounts/import")
async def import_accounts(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    file_bytes = await file.read()
    try:
        result = manager.import_accounts(file_bytes)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"分隔符正则无效: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(
        f"导入 {result['imported']} 条，新增/变更 {result['changed']} 条",
        result,
    )


@app.post("/api/accounts/receive")
def receive_accounts(
    payload: AccountBatchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    queued = manager.start_receive_batch(resolve_targets(payload))
    return ok(f"收件任务已加入队列，共 {queued} 个邮箱", {"queued": queued})


@app.post("/api/accounts/relogin")
def relogin_accounts(
    payload: AccountBatchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    queued = manager.start_relogin_batch(resolve_targets(payload))
    return ok(f"重新登录任务已加入队列，共 {queued} 个邮箱", {"queued": queued})


@app.post("/api/accounts/delete")
def delete_accounts(
    payload: AccountBatchRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    deleted = manager.delete_accounts(set(payload.emails))
    return ok(f"已删除 {deleted} 个邮箱及其本地缓存", {"deleted": deleted})


@app.patch("/api/accounts/flag")
def update_account_flag(
    payload: FlagRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        manager.set_flag(payload.email, payload.flag_color)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok("旗标已更新")


@app.post("/api/groups")
def create_group(
    payload: GroupRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        groups = manager.create_group(payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("分组已创建", {"custom_groups": groups})


@app.put("/api/groups")
def update_group(
    payload: GroupUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        groups = manager.update_group(
            payload.original_name,
            payload.name,
            payload.color,
            payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("分组已更新", {"custom_groups": groups})


@app.delete("/api/groups")
def delete_group(
    name: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        groups = manager.delete_group(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("分组已删除", {"custom_groups": groups})


@app.post("/api/tags")
def create_tag(
    payload: TagRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        tags = manager.create_tag(payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("标签已创建", {"custom_tags": tags})


@app.put("/api/tags")
def update_tag(
    payload: TagUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        tags = manager.update_tag(
            payload.original_name,
            payload.name,
            payload.color,
            payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("标签已更新", {"custom_tags": tags})


@app.delete("/api/tags")
def delete_tag(
    name: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        tags = manager.delete_tag(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("标签已删除", {"custom_tags": tags})


@app.patch("/api/accounts/group")
def assign_account_group(
    payload: AccountGroupRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        manager.assign_group(payload.email, payload.group_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("邮箱分组已更新")


@app.patch("/api/accounts/tags")
def set_account_tags(
    payload: AccountTagsRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        tags = manager.set_account_tags(payload.email, payload.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("邮箱标签已更新", {"tags": tags})


@app.get("/api/accounts/detail")
def get_account_detail(
    email: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        detail = manager.get_account_detail(email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok("ok", {"account": detail})


@app.put("/api/accounts")
def update_account(
    payload: AccountUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        account = manager.update_account(payload.original_email, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("账号已更新", {"account": account})


@app.post("/api/accounts/graph-reauth/start")
def start_graph_reauth(
    payload: GraphReauthStartRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    account = manager.find_account(payload.email)
    if not account:
        raise HTTPException(status_code=404, detail="邮箱不存在")
    client_id = account.auth_code_or_client_id.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="当前账号缺少 Client ID，无法发起 Graph 重新授权")
    try:
        data = _post_form_json(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
            {
                "client_id": client_id,
                "scope": GRAPH_REAUTH_SCOPE,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"发起 Graph 授权失败: {exc}") from exc
    session = GraphReauthSession(
        session_id=uuid4().hex,
        email=account.email,
        client_id=client_id,
        device_code=str(data.get("device_code", "") or ""),
        user_code=str(data.get("user_code", "") or ""),
        verification_uri=str(
            data.get("verification_uri")
            or data.get("verification_uri_complete")
            or ""
        ),
        expires_at=time.time() + int(data.get("expires_in", 900) or 900),
        interval=max(3, int(data.get("interval", 5) or 5)),
        message=str(data.get("message", "") or "请按提示完成微软授权"),
        next_poll_at=time.time(),
    )
    if not session.device_code or not session.user_code or not session.verification_uri:
        raise HTTPException(status_code=400, detail="微软返回的授权参数不完整")
    graph_reauth_sessions[session.session_id] = session
    manager.log_event(
        "info",
        "graph_reauth",
        "start",
        account.email,
        "发起 Graph 重新授权",
        {"client_id": client_id},
    )
    return ok(
        "Graph 重新授权已开始",
        {
            **_serialize_graph_reauth_session(session),
            "password": account.password,
        },
    )


@app.get("/api/accounts/graph-reauth/status")
def graph_reauth_status(
    session_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    session = graph_reauth_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="授权会话不存在或已过期")
    session = _poll_graph_reauth_session(session)
    if session.status in {"completed", "failed", "expired"}:
        graph_reauth_sessions.pop(session.session_id, None)
    return ok("ok", _serialize_graph_reauth_session(session))


@app.post("/api/oauth/manual/start")
def start_manual_oauth(
    payload: ManualOauthStartRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    settings = manager.settings
    client_id = settings.oauth_client_id.strip()
    redirect_uri = settings.oauth_redirect_uri.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="请先在系统设置中填写 Client ID")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="请先在系统设置中填写 Redirect URI")
    email_addr = payload.email.strip().lower()
    if "@" not in email_addr:
        raise HTTPException(status_code=400, detail="邮箱格式无效")
    state = secrets.token_urlsafe(24)
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    session_id = uuid4().hex
    authorize_url = _build_authorize_url(client_id, redirect_uri, state, code_challenge)
    manual_oauth_sessions[session_id] = {
        "session_id": session_id,
        "email": email_addr,
        "password": payload.password,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_verifier": code_verifier,
        "expires_at": time.time() + 900,
    }
    manager.log_event(
        "info",
        "oauth_manual",
        "start",
        email_addr,
        "发起手动微软授权",
        {"client_id": client_id, "redirect_uri": redirect_uri},
    )
    return ok(
        "授权链接已生成",
        {
            "session_id": session_id,
            "authorize_url": authorize_url,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "expires_in": 900,
            "scope": MANUAL_OAUTH_SCOPE,
        },
    )


@app.post("/api/oauth/manual/complete")
def complete_manual_oauth(
    payload: ManualOauthCompleteRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    session = manual_oauth_sessions.get(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="授权会话不存在或已过期")
    if time.time() >= float(session["expires_at"]):
        manual_oauth_sessions.pop(payload.session_id, None)
        raise HTTPException(status_code=400, detail="授权会话已过期，请重新生成授权链接")

    callback_url = payload.callback_url.strip()
    parsed = urllib.parse.urlparse(callback_url)
    query = urllib.parse.parse_qs(parsed.query)
    if "error" in query:
        detail = query.get("error_description", query.get("error", ["授权失败"]))[0]
        raise HTTPException(status_code=400, detail=f"微软授权失败: {detail}")
    code = query.get("code", [""])[0].strip()
    state = query.get("state", [""])[0].strip()
    if not code:
        raise HTTPException(status_code=400, detail="回调地址中缺少 code 参数")
    if state != session["state"]:
        raise HTTPException(status_code=400, detail="state 校验失败，请重新生成授权链接")

    try:
        token_data = _post_form_json(
            f"{MICROSOFT_CONSUMERS_BASE_URL}/token",
            {
                "client_id": session["client_id"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": session["redirect_uri"],
                "code_verifier": session["code_verifier"],
            },
        )
    except ValueError as exc:
        manager.log_event(
            "error",
            "oauth_manual",
            "token_exchange_failed",
            str(session["email"]),
            "手动微软授权 token 交换失败",
            {
                "client_id": session["client_id"],
                "redirect_uri": session["redirect_uri"],
                "code_length": len(code),
                "session_age_seconds": round(time.time() - (float(session["expires_at"]) - 900), 2),
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=f"token 交换失败: {exc}") from exc

    refresh_token = str(token_data.get("refresh_token", "") or "")
    access_token = str(token_data.get("access_token", "") or "")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="微软返回中缺少 refresh_token，请确认应用权限包含 offline_access")
    if not access_token:
        raise HTTPException(status_code=400, detail="微软返回中缺少 access_token")

    try:
        profile = _get_graph_profile(access_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"获取微软账号信息失败: {exc}") from exc

    actual_email = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
    expected_email = str(session["email"]).strip().lower()
    if not actual_email or "@" not in actual_email:
        raise HTTPException(status_code=400, detail="微软未返回可识别的邮箱地址，请重试")
    if actual_email != expected_email:
        raise HTTPException(
            status_code=400,
            detail=f"授权账号与预填邮箱不一致：当前授权为 {actual_email}，预填为 {expected_email}",
        )

    with manager.lock:
        existing = manager.find_account(actual_email)
        if existing:
            existing.password = str(session["password"] or existing.password)
            existing.auth_code_or_client_id = str(session["client_id"])
            existing.token = refresh_token
            existing.status = "待登录"
            existing.last_error = ""
            existing.cached_access_token = ""
            existing.cached_access_expire_at = 0.0
            existing.cached_graph_access_token = ""
            existing.cached_graph_access_expire_at = 0.0
            target = existing
        else:
            target = MailAccount(
                email=actual_email,
                password=str(session["password"] or ""),
                auth_code_or_client_id=str(session["client_id"]),
                token=refresh_token,
                status="待登录",
            )
            manager.accounts.append(target)
        manager._save_accounts_state()
        manager.rebuild_mail_pool()
        manager.enqueue_login(target)
        manager.log_event(
            "info",
            "oauth_manual",
            "complete",
            actual_email,
            "手动微软授权成功",
            {"client_id": session["client_id"], "redirect_uri": session["redirect_uri"]},
        )

    manual_oauth_sessions.pop(payload.session_id, None)
    return ok(
        "微软授权成功，账号已加入列表并开始登录",
        {
            "email": actual_email,
            "client_id": session["client_id"],
            "has_password": bool(session["password"]),
        },
    )


@app.get("/api/settings")
def get_settings(current_user: dict = Depends(get_current_user)) -> dict:
    return ok("ok", manager.dashboard_state().get("settings", {}))


@app.put("/api/settings")
def update_settings(
    payload: SettingsRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        settings = manager.update_settings(payload.model_dump())
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"分隔符正则无效: {exc}") from exc
    return ok("设置已保存", settings)


@app.post("/api/token-refresh/run")
def run_token_refresh(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        result = manager.refresh_all_tokens()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("Token 全量刷新已完成", result)


@app.get("/api/token-refresh/history")
def get_token_refresh_history(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return ok("ok", {"items": manager.get_refresh_history(limit)})


@app.get("/api/accounts/export")
def export_accounts(
    group_name: str = Query(default="__all__"),
    emails: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
) -> Response:
    selected_emails = [item.strip() for item in emails.split(",") if item.strip()]
    text, filename = manager.export_accounts_text(
        emails=selected_emails or None,
        group_name=group_name,
    )
    manager.log_event("info", "export", "accounts", group_name or "custom", "导出邮箱账号", {"emails": selected_emails})
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/backup/run")
def run_backup(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        result = manager.backup_accounts_now()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("账号备份已完成", result)


@app.post("/api/backup/restore")
async def restore_backup(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    file_bytes = await file.read()
    try:
        result = manager.restore_backup(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("备份已恢复，账号正在重新登录", result)


@app.post("/api/notifications/test")
def send_test_notification(current_user: dict = Depends(get_current_user)) -> dict:
    try:
        manager.send_test_telegram_notification()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Telegram 发送失败: {exc}") from exc
    return ok("Telegram 测试通知已发送")


@app.post("/api/translate")
def translate_text(
    payload: TranslateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="正文为空，无法翻译")
    try:
        translated = _translate_to_chinese(text[:12000])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"翻译失败: {exc}") from exc
    return ok("翻译完成", {"translated_text": translated})


@app.get("/api/logs")
def list_logs(
    category: str = Query(default=""),
    level: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return ok(
        "ok",
        {
            "items": storage.list_logs(
                category=category.strip(),
                level=level.strip(),
                keyword=keyword.strip(),
                limit=limit,
            )
        },
    )


@app.post("/api/mails/open")
def open_mail(
    payload: MailOpenRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return ok("ok", manager.open_mail(payload.local_key))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/mails/body-status")
def body_status(
    local_key: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return ok("ok", manager.get_body_status(local_key))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/mails/raw-body")
def raw_body(
    payload: MailOpenRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        return ok("原始正文已加载", manager.load_raw_mail_body(payload.local_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/mails/star")
def toggle_mail_star(
    payload: MailStarRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        state = manager.toggle_mail_star(payload.local_key, payload.is_starred)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok("星标状态已更新", {"is_starred": state})


@app.get("/api/v1/overview")
def api_v1_overview(
    request: Request,
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    state = manager.dashboard_state()
    return api_ok("ok", {"overview": state["overview"], "queue": state["overview"].get("queue", {}), "settings": state["settings"]}, _request_id(request))


@app.get("/api/v1/accounts")
def api_v1_accounts(
    request: Request,
    group: str = Query(default=""),
    tag: str = Query(default=""),
    status: str = Query(default=""),
    auth_method: str = Query(default=""),
    keyword: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    with manager.lock:
        accounts = manager.accounts.copy()
        if group:
            accounts = [item for item in accounts if (item.group_name or "未分组") == group]
        if tag:
            accounts = [item for item in accounts if tag in item.tags]
        if status:
            accounts = [item for item in accounts if item.status == status]
        if auth_method:
            accounts = [item for item in accounts if item.auth_method == auth_method]
        if keyword:
            query = keyword.lower()
            accounts = [
                item for item in accounts
                if query in item.email.lower()
                or query in (item.group_name or "").lower()
                or query in item.status.lower()
            ]
        items = [_safe_account(account, index + 1) for index, account in enumerate(accounts)]
    return api_ok("ok", _paginate(items, page, page_size), _request_id(request))


@app.get("/api/v1/accounts/{email_addr}")
def api_v1_account_detail(
    request: Request,
    email_addr: str,
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    with manager.lock:
        account = manager.find_account(email_addr)
        if not account:
            raise HTTPException(status_code=404, detail="邮箱不存在")
        data = _safe_account(account, manager.accounts.index(account) + 1)
    return api_ok("ok", {"account": data}, _request_id(request))


@app.get("/api/v1/mails")
def api_v1_mails(
    request: Request,
    account: str = Query(default=""),
    group: str = Query(default=""),
    tag: str = Query(default=""),
    folder: str = Query(default=""),
    starred: Optional[bool] = Query(default=None),
    unread: Optional[bool] = Query(default=None),
    has_code: Optional[bool] = Query(default=None),
    keyword: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    api_user: dict = Depends(require_api_scope("read:mails")),
) -> dict:
    with manager.lock:
        allowed_accounts = {item.email: item for item in manager.accounts}
        mails = manager.all_mails.copy()
        if account:
            mails = [item for item in mails if item.account_email == account]
        if group:
            mails = [item for item in mails if allowed_accounts.get(item.account_email) and (allowed_accounts[item.account_email].group_name or "未分组") == group]
        if tag:
            mails = [item for item in mails if allowed_accounts.get(item.account_email) and tag in allowed_accounts[item.account_email].tags]
        if folder:
            mails = [item for item in mails if manager._folder_display_name(item.folder) == folder or item.folder == folder]
        if starred is not None:
            mails = [item for item in mails if item.is_starred is starred]
        if unread is not None:
            mails = [item for item in mails if item.is_unread is unread]
        if has_code is not None:
            mails = [item for item in mails if bool(item.verification_codes) is has_code]
        if keyword:
            query = keyword.lower()
            mails = [item for item in mails if query in item.account_email.lower() or query in item.subject.lower() or query in item.from_text.lower()]
        if date_from:
            try:
                start_dt = dt.datetime.fromisoformat(date_from)
                mails = [item for item in mails if item.date_value >= start_dt]
            except ValueError:
                raise HTTPException(status_code=400, detail="date_from 格式无效")
        if date_to:
            try:
                end_dt = dt.datetime.fromisoformat(date_to)
                mails = [item for item in mails if item.date_value <= end_dt]
            except ValueError:
                raise HTTPException(status_code=400, detail="date_to 格式无效")
        items = [_safe_mail(item) for item in mails]
    return api_ok("ok", _paginate(items, page, page_size), _request_id(request))


@app.get("/api/v1/mails/{local_key}")
def api_v1_mail_detail(
    request: Request,
    local_key: str,
    include_body: bool = Query(default=True),
    api_user: dict = Depends(require_api_scope("read:mails")),
) -> dict:
    with manager.lock:
        item = manager.mail_items.get(local_key)
        if not item:
            raise HTTPException(status_code=404, detail="邮件不存在")
        data = _safe_mail(item, include_body=include_body)
    return api_ok("ok", {"mail": data}, _request_id(request))


@app.get("/api/v1/mails/{local_key}/codes")
def api_v1_mail_codes(
    request: Request,
    local_key: str,
    api_user: dict = Depends(require_api_scope("read:mails")),
) -> dict:
    with manager.lock:
        item = manager.mail_items.get(local_key)
        if not item:
            raise HTTPException(status_code=404, detail="邮件不存在")
        codes = item.verification_codes
    return api_ok("ok", {"items": codes}, _request_id(request))


@app.get("/api/v1/codes")
def api_v1_codes(
    request: Request,
    account: str = Query(default=""),
    keyword: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=200),
    api_user: dict = Depends(require_api_scope("read:mails")),
) -> dict:
    with manager.lock:
        mails = [item for item in manager.all_mails if item.verification_codes]
        if account:
            mails = [item for item in mails if item.account_email == account]
        if keyword:
            query = keyword.lower()
            mails = [item for item in mails if query in item.subject.lower() or query in item.from_text.lower() or query in item.account_email.lower()]
        if date_from:
            try:
                start_dt = dt.datetime.fromisoformat(date_from)
                mails = [item for item in mails if item.date_value >= start_dt]
            except ValueError:
                raise HTTPException(status_code=400, detail="date_from 格式无效")
        if date_to:
            try:
                end_dt = dt.datetime.fromisoformat(date_to)
                mails = [item for item in mails if item.date_value <= end_dt]
            except ValueError:
                raise HTTPException(status_code=400, detail="date_to 格式无效")
        items = []
        for mail in mails:
            for code in mail.verification_codes:
                items.append(
                    {
                        **code,
                        "account_email": mail.account_email,
                        "subject": mail.subject,
                        "from_text": mail.from_text,
                        "received_at": mail.date_value.isoformat(),
                        "mail_key": mail.local_key,
                    }
                )
        items = items[:limit]
    return api_ok("ok", {"items": items}, _request_id(request))


@app.get("/api/v1/groups")
def api_v1_groups(
    request: Request,
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    groups = manager.dashboard_state()["settings"].get("custom_groups", [])
    return api_ok("ok", {"items": groups}, _request_id(request))


@app.post("/api/v1/groups")
def api_v1_create_group(
    request: Request,
    payload: ApiGroupRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        groups = manager.create_group(payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "create_group", payload.name, payload.model_dump())
    return api_ok("分组已创建", {"items": groups}, _request_id(request))


@app.patch("/api/v1/groups/{group_name}")
def api_v1_update_group(
    request: Request,
    group_name: str,
    payload: ApiGroupRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        groups = manager.update_group(group_name, payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "update_group", group_name, payload.model_dump())
    return api_ok("分组已更新", {"items": groups}, _request_id(request))


@app.delete("/api/v1/groups/{group_name}")
def api_v1_delete_group(
    request: Request,
    group_name: str,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        groups = manager.delete_group(group_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "delete_group", group_name)
    return api_ok("分组已删除，邮箱已归入未分组", {"items": groups}, _request_id(request))


@app.get("/api/v1/tags")
def api_v1_tags(
    request: Request,
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    tags = manager.dashboard_state()["settings"].get("custom_tags", [])
    return api_ok("ok", {"items": tags}, _request_id(request))


@app.post("/api/v1/tags")
def api_v1_create_tag(
    request: Request,
    payload: ApiTagRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.create_tag(payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "create_tag", payload.name, payload.model_dump())
    return api_ok("标签已创建", {"items": tags}, _request_id(request))


@app.patch("/api/v1/tags/{tag_name}")
def api_v1_update_tag(
    request: Request,
    tag_name: str,
    payload: ApiTagRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.update_tag(tag_name, payload.name, payload.color, payload.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "update_tag", tag_name, payload.model_dump())
    return api_ok("标签已更新", {"items": tags}, _request_id(request))


@app.delete("/api/v1/tags/{tag_name}")
def api_v1_delete_tag(
    request: Request,
    tag_name: str,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.delete_tag(tag_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "delete_tag", tag_name)
    return api_ok("标签已删除", {"items": tags}, _request_id(request))


@app.patch("/api/v1/accounts/{email_addr}/group")
def api_v1_account_group(
    request: Request,
    email_addr: str,
    payload: ApiAccountGroupRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        manager.assign_group(email_addr, payload.group_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "assign_group", email_addr, payload.model_dump())
    return api_ok("邮箱分组已更新", {"email": email_addr, "group_name": payload.group_name}, _request_id(request))


@app.patch("/api/v1/accounts/batch/group")
def api_v1_batch_group(
    request: Request,
    payload: ApiBatchGroupRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        changed = manager.batch_assign_group(payload.emails, payload.group_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "batch_assign_group", payload.group_name, payload.model_dump())
    return api_ok("批量分组已更新", {"changed": changed}, _request_id(request))


@app.put("/api/v1/accounts/{email_addr}/tags")
def api_v1_replace_tags(
    request: Request,
    email_addr: str,
    payload: ApiTagsRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.patch_account_tags(email_addr, payload.tags, "replace")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "replace_tags", email_addr, payload.model_dump())
    return api_ok("邮箱标签已覆盖", {"email": email_addr, "tags": tags}, _request_id(request))


@app.post("/api/v1/accounts/{email_addr}/tags")
def api_v1_add_tags(
    request: Request,
    email_addr: str,
    payload: ApiTagsRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.patch_account_tags(email_addr, payload.tags, "add")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "add_tags", email_addr, payload.model_dump())
    return api_ok("邮箱标签已添加", {"email": email_addr, "tags": tags}, _request_id(request))


@app.delete("/api/v1/accounts/{email_addr}/tags")
def api_v1_remove_tags(
    request: Request,
    email_addr: str,
    payload: ApiTagsRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        tags = manager.patch_account_tags(email_addr, payload.tags, "remove")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "remove_tags", email_addr, payload.model_dump())
    return api_ok("邮箱标签已移除", {"email": email_addr, "tags": tags}, _request_id(request))


@app.post("/api/v1/accounts/batch/tags")
def api_v1_batch_add_tags(
    request: Request,
    payload: ApiBatchTagsRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        changed = manager.batch_patch_account_tags(payload.emails, payload.tags, "add")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "batch_add_tags", "batch", payload.model_dump())
    return api_ok("批量标签已添加", {"changed": changed}, _request_id(request))


@app.delete("/api/v1/accounts/batch/tags")
def api_v1_batch_remove_tags(
    request: Request,
    payload: ApiBatchTagsRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        changed = manager.batch_patch_account_tags(payload.emails, payload.tags, "remove")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "batch_remove_tags", "batch", payload.model_dump())
    return api_ok("批量标签已移除", {"changed": changed}, _request_id(request))


@app.patch("/api/v1/accounts/{email_addr}/flag")
def api_v1_set_flag(
    request: Request,
    email_addr: str,
    payload: ApiFlagRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        manager.set_flag(email_addr, payload.flag_color)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "set_flag", email_addr, payload.model_dump())
    return api_ok("旗标已更新", {"email": email_addr, "flag_color": payload.flag_color}, _request_id(request))


@app.delete("/api/v1/accounts/{email_addr}/flag")
def api_v1_clear_flag(
    request: Request,
    email_addr: str,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    try:
        manager.set_flag(email_addr, "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "clear_flag", email_addr)
    return api_ok("旗标已取消", {"email": email_addr, "flag_color": ""}, _request_id(request))


@app.patch("/api/v1/accounts/batch/flag")
def api_v1_batch_set_flag(
    request: Request,
    payload: ApiBatchFlagRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    changed = manager.batch_set_flag(payload.emails, payload.flag_color)
    _api_audit(request, api_user, "batch_set_flag", "batch", payload.model_dump())
    return api_ok("批量旗标已更新", {"changed": changed}, _request_id(request))


@app.delete("/api/v1/accounts/batch/flag")
def api_v1_batch_clear_flag(
    request: Request,
    payload: ApiBatchFlagRequest,
    api_user: dict = Depends(require_api_scope("write:taxonomy")),
) -> dict:
    changed = manager.batch_set_flag(payload.emails, "")
    _api_audit(request, api_user, "batch_clear_flag", "batch", {"emails": payload.emails})
    return api_ok("批量旗标已取消", {"changed": changed}, _request_id(request))


@app.post("/api/v1/accounts/import")
def api_v1_import_accounts(
    request: Request,
    payload: ApiAccountImportRequest,
    api_user: dict = Depends(require_api_scope("write:accounts")),
) -> dict:
    if payload.mode != "text":
        raise HTTPException(status_code=400, detail="当前接口仅支持 mode=text")
    try:
        result = manager.import_accounts(payload.content.encode("utf-8"))
    except (ValueError, re.error) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "import_accounts", "text", {"imported": result.get("imported"), "changed": result.get("changed")})
    return api_ok("账号导入完成", result, _request_id(request))


@app.post("/api/v1/accounts/import-file")
async def api_v1_import_accounts_file(
    request: Request,
    file: UploadFile = File(...),
    api_user: dict = Depends(require_api_scope("write:accounts")),
) -> dict:
    file_bytes = await file.read()
    try:
        result = manager.import_accounts(file_bytes)
    except (ValueError, re.error) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "import_accounts_file", file.filename or "file", {"imported": result.get("imported"), "changed": result.get("changed")})
    return api_ok("账号导入完成", result, _request_id(request))


@app.post("/api/v1/tasks/receive")
def api_v1_receive(
    request: Request,
    payload: ApiTaskTargetRequest,
    api_user: dict = Depends(require_api_scope("task:receive")),
) -> dict:
    targets = _resolve_api_targets(payload)
    queued = manager.start_receive_batch(targets)
    _api_audit(request, api_user, "receive", "batch", {"queued": queued})
    return api_ok("收件任务已加入队列", {"queued": queued, "queue": manager.queue_details()}, _request_id(request))


@app.post("/api/v1/tasks/relogin")
def api_v1_relogin(
    request: Request,
    payload: ApiTaskTargetRequest,
    api_user: dict = Depends(require_api_scope("task:login")),
) -> dict:
    targets = _resolve_api_targets(payload)
    queued = manager.start_relogin_batch(targets)
    _api_audit(request, api_user, "relogin", "batch", {"queued": queued})
    return api_ok("重新登录任务已加入队列", {"queued": queued, "queue": manager.queue_details()}, _request_id(request))


@app.get("/api/v1/tasks")
def api_v1_tasks(
    request: Request,
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    return api_ok("ok", {"queue": manager.queue_details()}, _request_id(request))


@app.post("/api/v1/backups/run")
def api_v1_backup(
    request: Request,
    payload: ApiBackupRequest,
    api_user: dict = Depends(require_api_scope("task:backup")),
) -> dict:
    try:
        result = manager.backup_accounts_now(trigger_source="api")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _api_audit(request, api_user, "backup", "api", payload.model_dump())
    return api_ok("备份已完成", result, _request_id(request))


@app.post("/api/v1/notifications/send")
def api_v1_notify(
    request: Request,
    payload: ApiNotificationRequest,
    api_user: dict = Depends(require_api_scope("notify:send")),
) -> dict:
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="通知内容不能为空")
    try:
        manager.send_manual_notification(payload.title, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"通知发送失败: {exc}") from exc
    _api_audit(request, api_user, "notify_send", "telegram", {"title": payload.title})
    return api_ok("通知已发送", {}, _request_id(request))


@app.get("/api/v1/logs")
def api_v1_logs(
    request: Request,
    category: str = Query(default=""),
    level: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=1000),
    api_user: dict = Depends(require_api_scope("read:logs")),
) -> dict:
    return api_ok(
        "ok",
        {"items": storage.list_logs(category=category.strip(), level=level.strip(), keyword=keyword.strip(), limit=limit)},
        _request_id(request),
    )


@app.get("/api/v1/system/version")
def api_v1_system_version(
    request: Request,
    force: bool = Query(False),
    api_user: dict = Depends(require_api_scope("read:accounts")),
) -> dict:
    return api_ok("ok", _version_payload(force=force), _request_id(request))


WEB_DIST_DIR = Path("/app/frontend_dist")

if WEB_DIST_DIR.exists():
    assets_dir = WEB_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(WEB_DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        candidate = WEB_DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST_DIR / "index.html")
