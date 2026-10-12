"""Small SQLite database: settings, auth users, bans, playlists, usage counters."""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from .api import Track

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    play_mode TEXT NOT NULL DEFAULT 'everyone',      -- who may start songs: everyone | admins
    control_mode TEXT NOT NULL DEFAULT 'admins',     -- who may skip/pause/stop: admins | everyone
    clean_commands INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_seen INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS auth_users (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS banned_chats (chat_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sudo_users (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    duration INTEGER NOT NULL DEFAULT 0,
    channel TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT '',
    added_at INTEGER NOT NULL,
    UNIQUE(user_id, video_id)
);
CREATE TABLE IF NOT EXISTS chat_usage (day TEXT NOT NULL, chat_id INTEGER NOT NULL, plays INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, chat_id));
"""

PLAYLIST_MAX = 100
PLAY_MODES = ("everyone", "admins")
CONTROL_MODES = ("admins", "everyone")


class Store:
    def __init__(self, path: str, timezone: str = "Asia/Kolkata"):
        self.path = path
        self.tz = ZoneInfo(timezone)
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @asynccontextmanager
    async def _tx(self):
        async with self._lock:
            assert self._db is not None, "Store.open() was not called"
            try:
                yield self._db
                await self._db.commit()
            except BaseException:
                await self._db.rollback()
                raise

    async def _one(self, sql: str, args=()):
        async with self._lock:
            assert self._db is not None
            cur = await self._db.execute(sql, args)
            return await cur.fetchone()

    async def _all(self, sql: str, args=()):
        async with self._lock:
            assert self._db is not None
            cur = await self._db.execute(sql, args)
            return await cur.fetchall()

    # ── chats and users (also the audience for /broadcast) ───────────────
    async def touch_chat(self, chat_id: int) -> None:
        async with self._tx() as db:
            await db.execute("INSERT OR IGNORE INTO chats(chat_id, first_seen) VALUES(?,?)", (chat_id, int(time.time())))

    async def touch_user(self, user_id: int) -> bool:
        """Returns True the first time we ever see this user."""
        async with self._tx() as db:
            cur = await db.execute("INSERT OR IGNORE INTO users(user_id, first_seen) VALUES(?,?)", (user_id, int(time.time())))
            return cur.rowcount == 1

    async def forget_chat(self, chat_id: int) -> None:
        async with self._tx() as db:
            await db.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
            await db.execute("DELETE FROM auth_users WHERE chat_id=?", (chat_id,))

    async def chat_ids(self) -> list[int]:
        return [r["chat_id"] for r in await self._all("SELECT chat_id FROM chats ORDER BY chat_id")]

    async def user_ids(self) -> list[int]:
        return [r["user_id"] for r in await self._all("SELECT user_id FROM users ORDER BY user_id")]

    async def counts(self) -> dict:
        c = await self._one("SELECT COUNT(*) n FROM chats")
        u = await self._one("SELECT COUNT(*) n FROM users")
        p = await self._one("SELECT COUNT(*) n FROM playlists")
        return {"chats": c["n"], "users": u["n"], "playlist_songs": p["n"]}

    # ── per-chat settings ─────────────────────────────────────────────────
    async def settings(self, chat_id: int) -> dict:
        row = await self._one("SELECT play_mode, control_mode, clean_commands FROM chats WHERE chat_id=?", (chat_id,))
        if row is None:
            return {"play_mode": "everyone", "control_mode": "admins", "clean_commands": False}
        return {"play_mode": row["play_mode"], "control_mode": row["control_mode"], "clean_commands": bool(row["clean_commands"])}

    async def set_setting(self, chat_id: int, key: str, value) -> None:
        if key == "play_mode" and value not in PLAY_MODES:
            raise ValueError("bad play_mode")
        if key == "control_mode" and value not in CONTROL_MODES:
            raise ValueError("bad control_mode")
        if key == "clean_commands":
            value = 1 if value else 0
        if key not in ("play_mode", "control_mode", "clean_commands"):
            raise ValueError("unknown setting")
        await self.touch_chat(chat_id)
        async with self._tx() as db:
            await db.execute(f"UPDATE chats SET {key}=? WHERE chat_id=?", (value, chat_id))

    # ── auth users (non-admins allowed to control the player) ─────────────
    async def add_auth(self, chat_id: int, user_id: int) -> bool:
        async with self._tx() as db:
            cur = await db.execute("INSERT OR IGNORE INTO auth_users VALUES(?,?)", (chat_id, user_id))
            return cur.rowcount == 1

    async def remove_auth(self, chat_id: int, user_id: int) -> bool:
        async with self._tx() as db:
            cur = await db.execute("DELETE FROM auth_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            return cur.rowcount == 1

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return await self._one("SELECT 1 FROM auth_users WHERE chat_id=? AND user_id=?", (chat_id, user_id)) is not None

    async def auth_list(self, chat_id: int) -> list[int]:
        return [r["user_id"] for r in await self._all("SELECT user_id FROM auth_users WHERE chat_id=?", (chat_id,))]

    # ── bans and sudo ─────────────────────────────────────────────────────
    async def _set_flag(self, table: str, col: str, value: int, on: bool) -> bool:
        async with self._tx() as db:
            if on:
                cur = await db.execute(f"INSERT OR IGNORE INTO {table}({col}) VALUES(?)", (value,))
            else:
                cur = await db.execute(f"DELETE FROM {table} WHERE {col}=?", (value,))
            return cur.rowcount == 1

    async def _has_flag(self, table: str, col: str, value: int) -> bool:
        return await self._one(f"SELECT 1 FROM {table} WHERE {col}=?", (value,)) is not None

    async def ban_user(self, user_id: int, on: bool = True) -> bool:
        return await self._set_flag("banned_users", "user_id", user_id, on)

    async def is_user_banned(self, user_id: int) -> bool:
        return await self._has_flag("banned_users", "user_id", user_id)

    async def ban_chat(self, chat_id: int, on: bool = True) -> bool:
        return await self._set_flag("banned_chats", "chat_id", chat_id, on)

    async def is_chat_banned(self, chat_id: int) -> bool:
        return await self._has_flag("banned_chats", "chat_id", chat_id)

    async def set_sudo(self, user_id: int, on: bool = True) -> bool:
        return await self._set_flag("sudo_users", "user_id", user_id, on)

    async def is_sudo(self, user_id: int) -> bool:
        return await self._has_flag("sudo_users", "user_id", user_id)

    async def sudo_list(self) -> list[int]:
        return [r["user_id"] for r in await self._all("SELECT user_id FROM sudo_users")]

    async def banned_ids(self) -> tuple[list[int], list[int]]:
        u = [r["user_id"] for r in await self._all("SELECT user_id FROM banned_users")]
        c = [r["chat_id"] for r in await self._all("SELECT chat_id FROM banned_chats")]
        return u, c

    # ── personal playlists ────────────────────────────────────────────────
    async def playlist_add(self, user_id: int, t: Track) -> str:
        """Returns 'added', 'exists' or 'full'."""
        async with self._tx() as db:
            cur = await db.execute("SELECT COUNT(*) n FROM playlists WHERE user_id=?", (user_id,))
            if (await cur.fetchone())["n"] >= PLAYLIST_MAX:
                return "full"
            cur = await db.execute(
                "INSERT OR IGNORE INTO playlists(user_id, video_id, title, duration, channel, thumbnail, added_at) VALUES(?,?,?,?,?,?,?)",
                (user_id, t.id, t.title, t.duration, t.channel, t.thumbnail, int(time.time())),
            )
            return "added" if cur.rowcount == 1 else "exists"

    async def playlist_list(self, user_id: int) -> list[Track]:
        rows = await self._all("SELECT * FROM playlists WHERE user_id=? ORDER BY id", (user_id,))
        return [
            Track(id=r["video_id"], title=r["title"], duration=r["duration"], channel=r["channel"], thumbnail=r["thumbnail"],
                  link=f"https://www.youtube.com/watch?v={r['video_id']}")
            for r in rows
        ]

    async def playlist_remove(self, user_id: int, position: int) -> bool:
        rows = await self._all("SELECT id FROM playlists WHERE user_id=? ORDER BY id", (user_id,))
        if position < 1 or position > len(rows):
            return False
        async with self._tx() as db:
            await db.execute("DELETE FROM playlists WHERE id=?", (rows[position - 1]["id"],))
        return True

    async def playlist_clear(self, user_id: int) -> int:
        async with self._tx() as db:
            cur = await db.execute("DELETE FROM playlists WHERE user_id=?", (user_id,))
            return cur.rowcount

    # ── fair use: plays per chat per day ──────────────────────────────────
    def today(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    async def chat_plays_today(self, chat_id: int) -> int:
        row = await self._one("SELECT plays FROM chat_usage WHERE day=? AND chat_id=?", (self.today(), chat_id))
        return row["plays"] if row else 0

    async def add_chat_play(self, chat_id: int) -> int:
        day = self.today()
        async with self._tx() as db:
            await db.execute(
                "INSERT INTO chat_usage(day, chat_id, plays) VALUES(?,?,1) ON CONFLICT(day, chat_id) DO UPDATE SET plays=plays+1",
                (day, chat_id),
            )
            await db.execute("DELETE FROM chat_usage WHERE day < date(?, '-7 day')", (day,))
            cur = await db.execute("SELECT plays FROM chat_usage WHERE day=? AND chat_id=?", (day, chat_id))
            return (await cur.fetchone())["plays"]
