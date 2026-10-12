from SHUBHMUSIC.utils.decorators.sudo import power, target_id


def register(ctx):
    store = ctx.store

    @ctx.command("ban", group_only=False)
    async def ban(client, message):
        if not await power(ctx, message):
            return
        target = await target_id(ctx, message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username. For a group, use its numeric ID.")
        if ctx.is_owner(target) or await store.is_sudo(target):
            return await message.reply_text("I will not ban the owner or a sudo user.")
        if target < 0:
            await store.ban_chat(target, True)
            await ctx.player.stop(target)
            return await message.reply_text(f"🚫 Group <code>{target}</code> is banned.")
        await store.ban_user(target, True)
        await message.reply_text(f"🚫 User <code>{target}</code> is banned from the bot.")

    @ctx.command("unban", group_only=False)
    async def unban(client, message):
        if not await power(ctx, message):
            return
        target = await target_id(ctx, message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        gone = await (store.ban_chat(target, False) if target < 0 else store.ban_user(target, False))
        await message.reply_text("✅ Unbanned." if gone else "That one was not banned.")

    @ctx.command("banned", group_only=False)
    async def banned(client, message):
        if not await power(ctx, message):
            return
        users, chats = await store.banned_ids()
        if not users and not chats:
            return await message.reply_text("Nobody is banned.")
        lines = [f"👤 <code>{u}</code>" for u in users] + [f"👥 <code>{c}</code>" for c in chats]
        await message.reply_text("🚫 <b>Banned</b>\n" + "\n".join(lines[:60]))
