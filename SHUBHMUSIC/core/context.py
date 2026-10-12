"""Everything the handlers share, plus the small helpers every handler needs."""

from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from pyrogram import enums, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

log = logging.getLogger("SHUBHMUSIC.ctx")

PREFIXES = ["/", "!", "."]
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
URL_RE = re.compile(r"https?://\S+", re.I)


def find_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,>") if m else None


def classify(text: str) -> str:
    """'playlist' | 'video' | 'foreign' (a non-YouTube link) | 'search' (plain words)."""
    url = find_url(text)
    if not url:
        return "search"
    try:
        u = urlparse(url)
    except ValueError:
        return "foreign"
    host = (u.hostname or "").lower()
    if host not in YT_HOSTS:
        return "foreign"
    q = parse_qs(u.query)
    if "list" in q and ("v" not in q or u.path.startswith("/playlist")):
        return "playlist"
    return "video"


def display_name(user) -> str:
    if user is None:
        return "Anonymous admin"
    name = " ".join(x for x in (user.first_name, getattr(user, "last_name", None)) if x)
    return name or user.username or str(user.id)


def png_bytes(data: bytes, name: str = "card.jpg") -> io.BytesIO:
    bio = io.BytesIO(data)
    bio.name = name
    return bio


@dataclass
class Ctx:
    cfg: object
    app: object  # the bot's pyrogram Client
    api: object
    store: object
    player: object
    assistants: object
    cards: object
    started_at: float = field(default_factory=time.time)
    bot_username: str = ""
    commands: dict = field(default_factory=dict)
    callbacks: dict = field(default_factory=dict)
    search_cache: dict = field(default_factory=dict)  # token -> (user_id, tracks, expires)
    _cooldown: dict = field(default_factory=dict)
    _admin_cache: dict = field(default_factory=dict)

    # ── registration ──────────────────────────────────────────────────────
    def command(self, names, *, group_only: bool = True, private_only: bool = False):
        names = [names] if isinstance(names, str) else list(names)

        def deco(fn):
            async def wrapper(client, message):
                if not await self.admit(message):
                    return
                await fn(client, message)

            for n in names:
                self.commands[n] = fn
            flt = filters.command(names, prefixes=PREFIXES)
            if group_only:
                flt &= filters.group
            if private_only:
                flt &= filters.private
            self.app.add_handler(MessageHandler(wrapper, flt))
            return fn

        return deco

    def callback(self, prefix: str):
        def deco(fn):
            async def wrapper(client, query):
                try:
                    if query.from_user and await self.store.is_user_banned(query.from_user.id):
                        return await query.answer()
                    await fn(client, query)
                except Exception:
                    log.exception("callback %s failed", prefix)
                    try:
                        await query.answer("Something went wrong. Please try again.", show_alert=True)
                    except Exception:
                        pass

            self.callbacks[prefix] = fn
            self.app.add_handler(CallbackQueryHandler(wrapper, filters.regex(rf"^{re.escape(prefix)}:")))
            return fn

        return deco

    # ── middleware: bans, bookkeeping, flood control ──────────────────────
    async def admit(self, message) -> bool:
        user = message.from_user
        chat = message.chat
        if user is not None:
            if await self.store.is_user_banned(user.id) and not self.is_owner(user.id):
                return False
            now = time.monotonic()
            last = self._cooldown.get(user.id, 0.0)
            if now - last < self.cfg.command_cooldown_seconds:
                return False
            self._cooldown[user.id] = now
            if len(self._cooldown) > 5000:
                cutoff = now - 60
                self._cooldown = {k: v for k, v in self._cooldown.items() if v > cutoff}
            if chat.type == enums.ChatType.PRIVATE:
                if await self.store.touch_user(user.id):
                    await self.log_event(f"👤 New user: {user.mention} (<code>{user.id}</code>)")
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            if await self.store.is_chat_banned(chat.id):
                return False
            await self.store.touch_chat(chat.id)
            if user is not None and await self._cleaning(chat.id):
                try:
                    await message.delete()
                except Exception:
                    pass
        return True

    async def _cleaning(self, chat_id: int) -> bool:
        return (await self.store.settings(chat_id))["clean_commands"]

    async def log_event(self, text: str) -> None:
        if not self.cfg.log_chat_id:
            return
        try:
            await self.app.send_message(self.cfg.log_chat_id, text, parse_mode=enums.ParseMode.HTML)
        except Exception:
            log.debug("could not write to the log chat", exc_info=True)

    # ── who is who ────────────────────────────────────────────────────────
    def is_owner(self, user_id: int) -> bool:
        return user_id in self.cfg.owner_ids

    async def is_power(self, user_id: int) -> bool:
        """Owner or sudo."""
        return self.is_owner(user_id) or await self.store.is_sudo(user_id)

    async def is_admin(self, chat_id: int, user_id: int, *, fresh: bool = False) -> bool:
        key = (chat_id, user_id)
        hit = self._admin_cache.get(key)
        if hit and not fresh and time.monotonic() - hit[1] < 60:
            return hit[0]
        try:
            m = await self.app.get_chat_member(chat_id, user_id)
            ok = m.status in (enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR)
        except Exception:
            ok = False
        self._admin_cache[key] = (ok, time.monotonic())
        return ok

    def forget_admins(self, chat_id: int | None = None) -> None:
        if chat_id is None:
            self._admin_cache.clear()
        else:
            self._admin_cache = {k: v for k, v in self._admin_cache.items() if k[0] != chat_id}

    async def can(self, chat_id: int, user, need: str, *, sender_chat=None) -> bool:
        """need: 'play' | 'control' | 'admin' | 'owner'."""
        if sender_chat is not None and sender_chat.id == chat_id:  # anonymous admin
            return need != "owner"
        if user is None:
            return False
        uid = user.id
        if need == "owner":
            return self.is_owner(uid)
        if await self.is_power(uid):
            return True
        if need == "admin":
            return await self.is_admin(chat_id, uid)
        s = await self.store.settings(chat_id)
        mode = s["play_mode"] if need == "play" else s["control_mode"]
        if mode == "everyone":
            return True
        return await self.is_admin(chat_id, uid) or await self.store.is_auth(chat_id, uid)

    async def require(self, message, need: str) -> bool:
        ok = await self.can(message.chat.id, message.from_user, need, sender_chat=getattr(message, "sender_chat", None))
        if not ok:
            texts = {
                "owner": "👑 Only the bot owner can use this.",
                "admin": "👮 Only group admins can use this.",
                "play": "👮 Only admins (or users they authorised with /auth) can add songs here.",
                "control": "👮 Only admins (or users they authorised with /auth) can control the player.",
            }
            await message.reply_text(texts[need])
        return ok

    # ── small senders ─────────────────────────────────────────────────────
    async def say(self, chat_id: int, text: str, **kw):
        return await self.app.send_message(chat_id, text, parse_mode=enums.ParseMode.HTML, **kw)
