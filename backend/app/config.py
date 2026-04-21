from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    app_name: str = os.getenv("APP_NAME", "EasyMail")
    app_subtitle: str = os.getenv(
        "APP_SUBTITLE", "Compose 驱动的多邮箱 IMAP 管理平台"
    )
    app_description: str = os.getenv(
        "APP_DESCRIPTION",
        "面向多邮箱账号的统一收件、管理与日志排查平台。",
    )
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@easymail.local")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-secret")
    token_expire_hours: int = int(os.getenv("TOKEN_EXPIRE_HOURS", "168"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "/app/data"))
    cors_origins_raw: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins_raw.split(",") if item.strip()]

    @property
    def public_settings(self) -> dict:
        return {
            "site_name": self.app_name,
            "site_subtitle": self.app_subtitle,
            "site_description": self.app_description,
            "admin_email": self.admin_email,
        }


config = AppConfig()
