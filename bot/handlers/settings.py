from __future__ import annotations

from pyrogram import enums

from ..ui import keyboards
from ..ui.text import esc

TITLE = "⚙️ <b>Group settings</b>\nTap a setting to change it."


async def resolve_user(ctx, message):
    """The target user of /auth, /ban...: a reply, an @username or a numeric ID."""
    rep = getattr(message, "reply_to_message", None)
    if rep is not None and rep.from_user is not None:
        return rep.from_user
    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        return None
    ref = parts[1].strip().split()[0]
    try:
        return await ctx.app.get_users(int(ref) if ref.lstrip("-").isdigit() else ref)
    except Exception:
        return None


def register(ctx):
    store = ctx.store

    @ctx.command("settings")
    async def settings_cmd(client, message):
        if not await ctx.require(message, "admin"):
            return
        await message.reply_text(TITLE, reply_markup=keyboards.settings(await store.settings(message.chat.id)))

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
        await query.message.edit_text(TITLE, reply_markup=keyboards.settings(await store.settings(chat_id)))
        await query.answer("Saved")

    @ctx.command("auth")
    async def auth(client, message):
        if not await ctx.require(message, "admin"):
            return
        target = await resolve_user(ctx, message)
        if target is None:
            return await message.reply_text("Reply to a user, or use <code>/auth @username</code>.")
        added = await store.add_auth(message.chat.id, target.id)
        await message.reply_text(f"✅ {target.mention} can now control the player." if added else f"{target.mention} is already authorised.")

    @ctx.command("unauth")
    async def unauth(client, message):
        if not await ctx.require(message, "admin"):
            return
        target = await resolve_user(ctx, message)
        if target is None:
            return await message.reply_text("Reply to a user, or use <code>/unauth @username</code>.")
        gone = await store.remove_auth(message.chat.id, target.id)
        await message.reply_text(f"🗑 {target.mention} can no longer control the player." if gone else f"{target.mention} was not authorised.")

    @ctx.command("authusers")
    async def authusers(client, message):
        ids = await store.auth_list(message.chat.id)
        if not ids:
            return await message.reply_text("Nobody is authorised yet. Admins can always control the player.")
        await message.reply_text("👥 <b>Authorised users</b>\n" + "\n".join(f"• <a href='tg://user?id={i}'>{i}</a>" for i in ids))

    @ctx.command(["reload", "admincache"])
    async def reload(client, message):
        ctx.forget_admins(message.chat.id)
        ctx.assistants.forget(message.chat.id)
        await message.reply_text("🔄 Admin list refreshed.")
