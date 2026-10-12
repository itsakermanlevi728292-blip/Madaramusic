from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.decorators.admins import gate, need_active
from SHUBHMUSIC.utils.formatters import esc


def register(ctx):
    player = ctx.player

    @ctx.command(["skip", "next"])
    async def skip(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        res = await player.skip(message.chat.id)
        if res and res[1] is None:
            return  # the notifier already said the queue finished
        if res:
            await message.reply_text(f"⏭ Skipped <b>{esc(text.short(res[0].title, 50))}</b>.")

    @ctx.command(["stop", "end"])
    async def stop(client, message):
        if not await gate(ctx, message):
            return
        ok = await player.stop(message.chat.id)
        await message.reply_text("⏹ Stopped and cleared the queue." if ok else "Nothing is playing right now.")
