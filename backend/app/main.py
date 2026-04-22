from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import create_access_token, get_current_user
from .config import config
from .manager import MailManager
from .models import DEFAULT_IMPORT_DELIMITERS
from .storage import SqliteStorage

GRAPH_REAUTH_SCOPE = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"

storage = SqliteStorage(config.data_dir)
manager = MailManager(storage)

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


class LoginRequest(BaseModel):
    email: str
    password: str


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


class GraphReauthStartRequest(BaseModel):
    email: str


class MailOpenRequest(BaseModel):
    local_key: str


class MailStarRequest(BaseModel):
    local_key: str
    is_starred: Optional[bool] = None


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


def ok(message: str, data: Optional[dict] = None) -> dict:
    return {"success": True, "message": message, "data": data or {}}


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


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    if payload.email != config.admin_email or payload.password != config.admin_password:
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
    return ok("Graph 重新授权已开始", _serialize_graph_reauth_session(session))


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
