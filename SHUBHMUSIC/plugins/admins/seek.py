from SHUBHMUSIC.utils.decorators.admins import gate, need_active
from SHUBHMUSIC.utils.exceptions import BotError
from SHUBHMUSIC.utils.formatters import esc, fmt_time, parse_time


def register(ctx):
    player = ctx.player

    async def do_seek(message, sign: int):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        parts = (message.text or "").split(None, 1)
        raw = parts[1].strip() if len(parts) > 1 else ""
        q = player.queue(message.chat.id)
        try:
            if sign == 0:  # /seek: absolute (1:30) or relative (+30 / -30)
                if raw[:1] in "+-" and raw[1:].isdigit():
                    target = await player.seek(message.chat.id, delta=int(raw))
                else:
                    secs = parse_time(raw)
                    if secs is None:
                        return await message.reply_text("Use <code>/seek 1:30</code>, <code>/seek +30</code> or <code>/seek -15</code>.")
                    target = await player.seek(message.chat.id, absolute=secs)
            else:
                secs = int(raw) if raw.isdigit() else 15
                target = await player.seek(message.chat.id, delta=sign * secs)
        except BotError as e:
            return await message.reply_text("⚠️ " + esc(str(e)))
        if target is None:
            return await message.reply_text("I can't jump there: it is past the end of the song, or the length is unknown.")
        await message.reply_text(f"⏩ Jumped to <b>{fmt_time(target)}</b> / {fmt_time(q.current.duration)}.")

    @ctx.command("seek")
    async def seek(client, message):
        await do_seek(message, 0)

    @ctx.command("seekback")
    async def seekback(client, message):
        await do_seek(message, -1)

    @ctx.command("seekfwd")
    async def seekfwd(client, message):
        await do_seek(message, 1)
