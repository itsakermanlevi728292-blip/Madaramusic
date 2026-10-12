"""Makes sure the assistant account is inside the group before we try to join its voice chat."""

from __future__ import annotations

import asyncio
import logging

from pyrogram import enums
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    InviteHashExpired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
)

from .errors import AssistantError

log = logging.getLogger("bot.assistant")


class AssistantManager:
    def __init__(self, bot, userbots: list):
        self.bot = bot
        self.userbots = userbots
        self._ids: dict[int, int] = {}
        self._joined: set[tuple[int, int]] = set()
        self._locks: dict[int, asyncio.Lock] = {}

    def userbot_for(self, chat_id: int):
        return self.userbots[abs(int(chat_id)) % len(self.userbots)]

    async def username_of(self, chat_id: int) -> str:
        me = await self.userbot_for(chat_id).get_me()
        return me.username or me.first_name

    async def _me_id(self, ub) -> int:
        key = id(ub)
        if key not in self._ids:
            self._ids[key] = (await ub.get_me()).id
        return self._ids[key]

    async def ensure_present(self, chat_id: int) -> None:
        ub = self.userbot_for(chat_id)
        marker = (chat_id, id(ub))
        if marker in self._joined:
            return
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            if marker in self._joined:
                return
            await self._join(chat_id, ub)
            self._joined.add(marker)

    def forget(self, chat_id: int) -> None:
        self._joined = {m for m in self._joined if m[0] != chat_id}

    async def _is_member(self, ub, chat_id: int) -> bool:
        try:
            member = await ub.get_chat_member(chat_id, "me")
        except UserNotParticipant:
            return False
        except Exception:
            return False
        if member.status in (enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT):
            return False
        if member.status == enums.ChatMemberStatus.RESTRICTED:
            return bool(getattr(member, "is_member", True))
        return True

    async def _join(self, ub, chat_id: int) -> None:
        if await self._is_member(ub, chat_id):
            return
        me_id = await self._me_id(ub)
        try:
            bot_member = await self.bot.get_chat_member(chat_id, "me")
        except Exception:
            raise AssistantError("Make me an admin of this group first, then try again.")
        if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
            raise AssistantError("Make me an admin (with “Invite users”) so my assistant can join, then try again.")
        # an assistant that was banned must be unbanned before it can join again
        try:
            member = await self.bot.get_chat_member(chat_id, me_id)
            if member.status == enums.ChatMemberStatus.BANNED:
                await self.bot.unban_chat_member(chat_id, me_id)
        except Exception:
            pass
        try:
            chat = await self.bot.get_chat(chat_id)
            target = chat.username or await self.bot.export_chat_invite_link(chat_id)
        except ChatAdminRequired:
            raise AssistantError("I need the “Invite users via link” permission so my assistant can join.")
        except Exception as e:
            log.warning("could not get an invite link for %s: %s", chat_id, e)
            raise AssistantError("I could not create an invite link. Give me the “Invite users” admin permission.")
        for attempt in range(2):
            try:
                await ub.join_chat(target)
                return
            except UserAlreadyParticipant:
                return
            except InviteRequestSent:
                try:
                    await self.bot.approve_chat_join_request(chat_id, me_id)
                    return
                except Exception:
                    raise AssistantError("My assistant asked to join. Approve its join request, then try again.")
            except InviteHashExpired:
                raise AssistantError("The invite link is not valid. Revoke old links or give me the “Invite users” permission.")
            except FloodWait as e:
                if attempt == 0 and e.value <= 15:
                    await asyncio.sleep(e.value + 1)
                    continue
                raise AssistantError(f"Telegram asked my assistant to wait {e.value}s before joining. Try again later.")
            except Exception as e:
                log.warning("assistant join failed in %s: %s", chat_id, e)
                raise AssistantError("My assistant could not join this group. Add it manually, then try again.")
