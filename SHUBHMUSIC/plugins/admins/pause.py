from SHUBHMUSIC.utils.decorators.admins import gate, need_active


def register(ctx):
    player = ctx.player

    @ctx.command("pause")
    async def pause(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        ok = await player.pause(message.chat.id)
        await message.reply_text("⏸ Paused." if ok else "It is already paused.")

    @ctx.command("resume")
    async def resume(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        ok = await player.resume(message.chat.id)
        await message.reply_text("▶️ Resumed." if ok else "It is not paused.")
