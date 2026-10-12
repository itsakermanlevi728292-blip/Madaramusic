"""Turns player events into Telegram messages (the now-playing card, errors, "queue finished")."""

from __future__ import annotations

import logging

from pyrogram import enums

from .context import png_bytes
from .queue import ChatQueue
from .ui import keyboards, text

log = logging.getLogger("bot.notifier")

FINISH_TEXT = {
    "queue_ended": "✅ <b>Queue finished.</b> I left the voice chat. Add more with /play.",
    "alone": "👋 Everyone left the voice chat, so I left too.",
    "call_closed": "🔇 The voice chat ended, so I cleared the queue.",
    "errors": "⚠️ Several songs in a row could not be played, so I stopped.",
}


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
        markup = keyboards.player(q)
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
        msg = FINISH_TEXT.get(reason)
        if msg:
            await self.ctx.say(chat_id, msg)

    async def failed(self, chat_id: int, message: str) -> None:
        await self.ctx.say(chat_id, "⚠️ " + text.esc(message))

    async def limit_reached(self, chat_id: int, retry_after: int) -> None:
        await self._drop_old_card(chat_id, self.ctx.player.queue(chat_id))
        await self.ctx.say(chat_id, text.limit_message(retry_after))
        await self.ctx.log_event("⚠️ The API key hit its daily song limit. Upgrade the plan on your API server.")
