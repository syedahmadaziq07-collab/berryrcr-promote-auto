"""
services/sqlite_storage.py — SQLite-based FSM storage untuk aiogram 3.
Menggantikan MemoryStorage supaya FSM state kekal selepas bot restart.
Menggunakan Python built-in sqlite3 + asyncio.to_thread (tiada pakej tambahan).
"""

import asyncio
import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

logger = logging.getLogger(__name__)


class SQLiteStorage(BaseStorage):
    """
    Persistent FSM storage menggunakan SQLite.
    State dan data kekal dalam fail DB walaupun bot restart.
    """

    def __init__(self, db_path: str = "fsm_storage.db"):
        self._db_path = db_path
        self._init_db()
        logger.info("SQLiteStorage: diinisialisasi — db=%s", db_path)

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm (
                    key   TEXT PRIMARY KEY,
                    state TEXT,
                    data  TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.commit()

    @staticmethod
    def _make_key(k: StorageKey) -> str:
        destiny = k.destiny if k.destiny else "default"
        return f"{k.bot_id}:{k.chat_id}:{k.user_id}:{destiny}"

    # ── sync helpers (dijalankan dalam thread pool) ──

    def _sync_set_state(self, key: str, state: Optional[str]):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO fsm(key, state, data) VALUES(?, ?, '{}')"
                " ON CONFLICT(key) DO UPDATE SET state = excluded.state",
                (key, state),
            )
            conn.commit()

    def _sync_get_state(self, key: str) -> Optional[str]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT state FROM fsm WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def _sync_set_data(self, key: str, data_json: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "INSERT INTO fsm(key, state, data) VALUES(?, NULL, ?)"
                " ON CONFLICT(key) DO UPDATE SET data = excluded.data",
                (key, data_json),
            )
            conn.commit()

    def _sync_get_data(self, key: str) -> str:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT data FROM fsm WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else "{}"

    # ── aiogram BaseStorage interface ──

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_str = state.state if hasattr(state, "state") else state
        k = self._make_key(key)
        await asyncio.to_thread(self._sync_set_state, k, state_str)
        logger.debug("FSM set_state: key=%s state=%s", k, state_str)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        k = self._make_key(key)
        result = await asyncio.to_thread(self._sync_get_state, k)
        logger.debug("FSM get_state: key=%s → %s", k, result)
        return result

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        k = self._make_key(key)
        await asyncio.to_thread(self._sync_set_data, k, json.dumps(data))

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        k = self._make_key(key)
        raw = await asyncio.to_thread(self._sync_get_data, k)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    async def close(self) -> None:
        logger.info("SQLiteStorage: ditutup.")
