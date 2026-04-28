from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _hash_password(password: str, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_urlsafe(24)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        260000,
    )
    return f"pbkdf2_sha256$260000${salt_value}${base64.b64encode(digest).decode('ascii')}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, encoded = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_text),
        )
        return secrets.compare_digest(base64.b64encode(digest).decode("ascii"), encoded)
    except Exception:
        return False


def _random_admin_email() -> str:
    return f"admin-{secrets.token_hex(4)}@easymail.local"


def _random_password() -> str:
    return secrets.token_urlsafe(24)


def _load_or_create_runtime_config(data_dir: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = data_dir / "runtime_config.json"
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload, None
        except Exception:
            pass

    generated_password = os.getenv("ADMIN_PASSWORD") or _random_password()
    generated_admin_email = os.getenv("ADMIN_EMAIL") or _random_admin_email()
    payload = {
        "admin_email": generated_admin_email,
        "admin_password_hash": _hash_password(generated_password),
        "jwt_secret": os.getenv("JWT_SECRET") or secrets.token_urlsafe(48),
        "token_expire_hours": int(os.getenv("TOKEN_EXPIRE_HOURS", "168") or "168"),
    }
    tmp_path = config_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(config_path)
    return payload, {"admin_email": generated_admin_email, "admin_password": generated_password}


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    app_subtitle: str
    app_description: str
    admin_email: str
    admin_password_hash: str
    jwt_secret: str
    token_expire_hours: int
    data_dir: Path
    cors_origins_raw: str
    generated_credentials: dict[str, str] | None = None

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

    def verify_admin_password(self, password: str) -> bool:
        return _verify_password(password, self.admin_password_hash)


def _build_config() -> AppConfig:
    data_dir = Path(os.getenv("DATA_DIR", "/app/data"))
    runtime_config, generated_credentials = _load_or_create_runtime_config(data_dir)
    return AppConfig(
        app_name=os.getenv("APP_NAME", "EasyMail"),
        app_subtitle=os.getenv("APP_SUBTITLE", "Compose 驱动的多邮箱 IMAP 管理平台"),
        app_description=os.getenv("APP_DESCRIPTION", "面向多邮箱账号的统一收件、管理与日志排查平台。"),
        admin_email=str(runtime_config.get("admin_email") or "admin@easymail.local"),
        admin_password_hash=str(runtime_config.get("admin_password_hash") or ""),
        jwt_secret=str(runtime_config.get("jwt_secret") or secrets.token_urlsafe(48)),
        token_expire_hours=int(runtime_config.get("token_expire_hours", 168) or 168),
        data_dir=data_dir,
        cors_origins_raw=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"),
        generated_credentials=generated_credentials,
    )


config = _build_config()
