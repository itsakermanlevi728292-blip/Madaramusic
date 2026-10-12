from __future__ import annotations

from pyrogram import enums

from SHUBHMUSIC.utils.inline.settings import settings_markup
from SHUBHMUSIC.utils.formatters import esc

TITLE = "⚙️ <b>Group settings</b>\nTap a setting to change it."


def register(ctx):
    store = ctx.store

    @ctx.command("settings")
    async def settings_cmd(client, message):
        if not await ctx.require(message, "admin"):
            return
        await message.reply_text(TITLE, reply_markup=settings_markup(await store.settings(message.chat.id)))

    @ctx.callback("st")
    async def settings_cb(client, query):
        chat_id, action = query.message.chat.id, query.data.split(":", 1)[1]
        if not await ctx.can(chat_id, query.from_user, "admin"):
            return await query.answer("👮 Only admins can change settings.", show_alert=True)
        if action == "close":
            await query.message.delete()
            return await query.answer()
        s = await store.settings(chat_id)
        if action == "play":
            await store.set_setting(chat_id, "play_mode", "admins" if s["play_mode"] == "everyone" else "everyone")
        elif action == "control":
            await store.set_setting(chat_id, "control_mode", "admins" if s["control_mode"] == "everyone" else "everyone")
        elif action == "clean":
            await store.set_setting(chat_id, "clean_commands", not s["clean_commands"])
        await query.message.edit_text(TITLE, reply_markup=settings_markup(await store.settings(chat_id)))
        await query.answer("Saved")
