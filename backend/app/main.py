from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import create_access_token, get_current_user
from .config import config
from .manager import MailManager
from .storage import SqliteStorage

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


class MailOpenRequest(BaseModel):
    local_key: str


class MailStarRequest(BaseModel):
    local_key: str
    is_starred: Optional[bool] = None


class SettingsRequest(BaseModel):
    auto_receive_interval: int = 120
    txt_delimiter_preset: str = "dash3"
    txt_delimiter_regex: str = r"-{3,}"
    import_delimiters: list[str] = Field(default_factory=lambda: [r"-{3,}", r"\|\|", r"\|", r",", r";", r"\t"])
    txt_comment_prefix: str = "#"
    txt_skip_first_line: bool = False
    startup_auto_login: bool = True
    mail_list_limit: int = 0
    mark_read_on_open: bool = True
    custom_groups: list[str] = Field(default_factory=list)
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
