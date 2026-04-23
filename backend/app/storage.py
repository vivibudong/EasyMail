from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import (
    AppSettings,
    MailAccount,
    MailItem,
    account_from_dict,
    account_to_dict,
    mail_item_from_dict,
    mail_item_to_dict,
    settings_from_dict,
    settings_to_dict,
)


class SqliteStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "easymail.db"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS accounts (
                    email TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS read_state (
                    local_key TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mail_cache (
                    local_key TEXT PRIMARY KEY,
                    account_email TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    date_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_mail_cache_account_email
                ON mail_cache(account_email);

                CREATE INDEX IF NOT EXISTS idx_mail_cache_date_value
                ON mail_cache(date_value DESC);

                CREATE TABLE IF NOT EXISTS refresh_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    trigger_source TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_app_logs_created_at
                ON app_logs(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_app_logs_category
                ON app_logs(category);
                """
            )

    def load_accounts(self) -> list[MailAccount]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM accounts ORDER BY rowid ASC"
            ).fetchall()
        accounts: list[MailAccount] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except Exception:
                continue
            account = account_from_dict(payload)
            if account:
                accounts.append(account)
        return accounts

    def save_accounts(self, accounts: list[MailAccount]) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._connect() as connection:
            connection.execute("DELETE FROM accounts")
            connection.executemany(
                "INSERT INTO accounts(email, payload, updated_at) VALUES(?, ?, ?)",
                [
                    (
                        account.email,
                        json.dumps(account_to_dict(account), ensure_ascii=False),
                        now,
                    )
                    for account in accounts
                ],
            )

    def load_settings(self) -> AppSettings:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("app_settings",),
            ).fetchone()
        if row is None:
            return AppSettings()
        try:
            payload = json.loads(str(row["value"]))
        except Exception:
            return AppSettings()
        if not isinstance(payload, dict):
            return AppSettings()
        return settings_from_dict(payload)

    def save_settings(self, settings: AppSettings) -> None:
        now = dt.datetime.utcnow().isoformat()
        payload = json.dumps(settings_to_dict(settings), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                ("app_settings", payload, now),
            )

    def load_read_state(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT local_key FROM read_state").fetchall()
        return {str(row["local_key"]) for row in rows}

    def save_read_state(self, read_keys: set[str]) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._connect() as connection:
            connection.execute("DELETE FROM read_state")
            connection.executemany(
                "INSERT INTO read_state(local_key, updated_at) VALUES(?, ?)",
                [(item, now) for item in sorted(read_keys)],
            )

    def load_mail_cache(self, account: MailAccount, read_keys: set[str]) -> list[MailItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM mail_cache
                WHERE account_email = ?
                ORDER BY date_value DESC, rowid DESC
                """,
                (account.email,),
            ).fetchall()
        mails: list[MailItem] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except Exception:
                continue
            item = mail_item_from_dict(payload)
            if not item:
                continue
            if item.local_key in read_keys:
                item.is_unread = False
            mails.append(item)
        return mails

    def save_mail_cache(self, account: MailAccount) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM mail_cache WHERE account_email = ?",
                (account.email,),
            )
            connection.executemany(
                """
                INSERT INTO mail_cache(local_key, account_email, payload, date_value, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.local_key,
                        account.email,
                        json.dumps(mail_item_to_dict(item), ensure_ascii=False),
                        item.date_value.isoformat(),
                        now,
                    )
                    for item in account.mails
                ],
            )

    def remove_mail_cache(self, email_addr: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM mail_cache WHERE account_email = ?",
                (email_addr,),
            )

    def clear_mail_cache(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM mail_cache")

    def clear_read_state(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM read_state")

    def append_refresh_history(self, trigger_source: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO refresh_history(created_at, trigger_source, payload) VALUES(?, ?, ?)",
                (
                    dt.datetime.utcnow().isoformat(),
                    trigger_source,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def load_refresh_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, trigger_source, payload
                FROM refresh_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload"]))
            except Exception:
                payload = {}
            records.append(
                {
                    "id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "trigger_source": str(row["trigger_source"]),
                    "payload": payload,
                }
            )
        return records

    def save_task_state(self, key: str, value: dict[str, Any]) -> None:
        now = dt.datetime.utcnow().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_state(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), now),
            )

    def load_task_state(self, key: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM task_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(str(row["value"]))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def append_log(
        self,
        level: str,
        category: str,
        action: str,
        subject: str,
        message: str,
        detail: dict[str, Any] | str | None = None,
    ) -> None:
        detail_payload: str
        if isinstance(detail, str):
            detail_payload = detail
        else:
            detail_payload = json.dumps(detail or {}, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_logs(created_at, level, category, action, subject, message, detail)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dt.datetime.utcnow().isoformat(),
                    level,
                    category,
                    action,
                    subject,
                    message,
                    detail_payload,
                ),
            )

    def list_logs(
        self,
        *,
        category: str = "",
        level: str = "",
        keyword: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        values: list[Any] = []
        if category:
            where_clauses.append("category = ?")
            values.append(category)
        if level:
            where_clauses.append("level = ?")
            values.append(level)
        if keyword:
            where_clauses.append("(subject LIKE ? OR message LIKE ? OR detail LIKE ?)")
            pattern = f"%{keyword}%"
            values.extend([pattern, pattern, pattern])
        sql = """
            SELECT id, created_at, level, category, action, subject, message, detail
            FROM app_logs
        """
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        values.append(limit)

        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            detail_value = str(row["detail"])
            parsed_detail: Any
            try:
                parsed_detail = json.loads(detail_value)
            except Exception:
                parsed_detail = detail_value
            items.append(
                {
                    "id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "level": str(row["level"]),
                    "category": str(row["category"]),
                    "action": str(row["action"]),
                    "subject": str(row["subject"]),
                    "message": str(row["message"]),
                    "detail": parsed_detail,
                }
            )
        return items
