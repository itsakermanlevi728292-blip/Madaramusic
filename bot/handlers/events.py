"""Group lifecycle: the bot gets added to / removed from a group."""

from __future__ import annotations

import logging

from pyrogram import enums, filters
from pyrogram.handlers import ChatMemberUpdatedHandler, MessageHandler

from ..ui.text import esc

log = logging.getLogger("bot.events")

WELCOME = (
    "🎧 <b>Thanks for adding me!</b>\n\n"
    "1. Make me an <b>admin</b> (Invite users + Manage voice chats)\n"
    "2. Start a voice chat\n"
    "3. Send <code>/play song name</code>\n\n"
    "My assistant account joins by itself. See /help for everything I can do."
)


def register(ctx):
    store = ctx.store

    async def bot_status_changed(client, update):
        old, new = update.old_chat_member, update.new_chat_member
        chat = update.chat
        if new is None or not new.user or not new.user.is_self:
            return
        if chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            return
        gone = new.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED)
        was_gone = old is None or old.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED)
        if gone:
            await ctx.player.stop(chat.id)
            ctx.player.queues.pop(chat.id, None)
            ctx.assistants.forget(chat.id)
            ctx.forget_admins(chat.id)
            await store.forget_chat(chat.id)
            await ctx.log_event(f"➖ Removed from <b>{esc(chat.title)}</b> (<code>{chat.id}</code>)")
        elif was_gone:
            if await store.is_chat_banned(chat.id):
                try:
                    await client.leave_chat(chat.id)
                except Exception:
                    pass
                return
            await store.touch_chat(chat.id)
            try:
                await ctx.say(chat.id, WELCOME)
            except Exception:
                pass
            await ctx.log_event(f"➕ Added to <b>{esc(chat.title)}</b> (<code>{chat.id}</code>)")
        else:
            ctx.forget_admins(chat.id)  # promoted or demoted: refresh what we know

    ctx.app.add_handler(ChatMemberUpdatedHandler(bot_status_changed))

    async def admins_changed(client, update):
        ctx.forget_admins(update.chat.id)

    ctx.app.add_handler(ChatMemberUpdatedHandler(admins_changed), group=1)

    async def video_chat_ended(client, message):
        # When the voice chat is closed Telegram posts a service message; drop the queue.
        if message.video_chat_ended is not None:
            await ctx.player.on_call_closed(message.chat.id)

    ctx.app.add_handler(MessageHandler(video_chat_ended, filters.video_chat_ended & filters.group))
