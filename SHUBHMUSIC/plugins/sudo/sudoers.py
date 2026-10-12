from SHUBHMUSIC.utils.decorators.sudo import owner_only, power, target_id


def register(ctx):
    store = ctx.store

    @ctx.command("sudo", group_only=False)
    async def sudo(client, message):
        if not await owner_only(ctx, message):
            return
        target = await target_id(ctx, message)
        if target is None or target < 0:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        added = await store.set_sudo(target, True)
        await message.reply_text(f"✅ <code>{target}</code> is now a sudo user." if added else "Already a sudo user.")

    @ctx.command("unsudo", group_only=False)
    async def unsudo(client, message):
        if not await owner_only(ctx, message):
            return
        target = await target_id(ctx, message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        gone = await store.set_sudo(target, False)
        await message.reply_text("🗑 Sudo removed." if gone else "That user was not sudo.")

    @ctx.command("sudolist", group_only=False)
    async def sudolist(client, message):
        if not await power(ctx, message):
            return
        owners = sorted(ctx.cfg.owner_ids)
        sudos = await store.sudo_list()
        lines = [f"👑 <code>{i}</code>" for i in owners] + [f"🛡 <code>{i}</code>" for i in sudos]
        await message.reply_text("🛡 <b>Owner &amp; sudo</b>\n" + ("\n".join(lines) if lines else "None"))
