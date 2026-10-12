"""Turns player events into Telegram messages (the now-playing card, errors, "queue finished")."""

from __future__ import annotations

import logging

from pyrogram import enums

from SHUBHMUSIC.core.context import png_bytes
from SHUBHMUSIC.utils.stream.queue import ChatQueue
from strings import FINISH
from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.inline.play import player_markup

log = logging.getLogger("SHUBHMUSIC.notifier")



class TelegramNotifier:
    def __init__(self, ctx):
        self.ctx = ctx

    async def _drop_old_card(self, chat_id: int, q: ChatQueue) -> None:
        if q.last_message_id:
            try:
                await self.ctx.app.delete_messages(chat_id, q.last_message_id)
            except Exception:
                pass
            q.last_message_id = None

    async def now_playing(self, chat_id: int, q: ChatQueue) -> None:
        t = q.current
        if t is None:
            return
        await self._drop_old_card(chat_id, q)
        caption = text.now_playing(q, self.ctx.cfg.bot_name)
        markup = player_markup(q)
        data = await self.ctx.cards.make(t, t.requested_name)
        try:
            if data:
                msg = await self.ctx.app.send_photo(chat_id, png_bytes(data), caption=caption, reply_markup=markup,
                                                    parse_mode=enums.ParseMode.HTML)
            else:
                msg = await self.ctx.say(chat_id, caption, reply_markup=markup)
            q.last_message_id = msg.id
        except Exception:
            log.exception("could not send the now-playing card to %s", chat_id)

    async def finished(self, chat_id: int, reason: str) -> None:
        q = self.ctx.player.queue(chat_id)
        await self._drop_old_card(chat_id, q)
        msg = FINISH.get(reason)
        if msg:
            await self.ctx.say(chat_id, msg)

    async def failed(self, chat_id: int, message: str) -> None:
        await self.ctx.say(chat_id, "⚠️ " + text.esc(message))

    async def limit_reached(self, chat_id: int, retry_after: int) -> None:
        await self._drop_old_card(chat_id, self.ctx.player.queue(chat_id))
        await self.ctx.say(chat_id, text.limit_message(retry_after))
        await self.ctx.log_event("⚠️ The API key hit its daily song limit. Upgrade the plan on your API server.")
