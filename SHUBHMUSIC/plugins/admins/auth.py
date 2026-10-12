from SHUBHMUSIC.utils.extraction import resolve_user


def register(ctx):
    store = ctx.store

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
