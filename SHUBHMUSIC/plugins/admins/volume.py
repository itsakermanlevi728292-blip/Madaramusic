import logging

from SHUBHMUSIC.utils.decorators.admins import gate, need_active

log = logging.getLogger("SHUBHMUSIC.volume")


def register(ctx):
    player = ctx.player

    @ctx.command(["volume", "vol"])
    async def volume(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            q = player.queue(message.chat.id)
            return await message.reply_text(f"🔊 Volume is <b>{q.volume}%</b>. Change it with <code>/volume 1-200</code>.")
        try:
            v = await player.set_volume(message.chat.id, int(parts[1]))
        except Exception:
            log.exception("volume failed")
            return await message.reply_text("⚠️ Could not change the volume right now.")
        await message.reply_text(f"🔊 Volume set to <b>{v}%</b>.")
