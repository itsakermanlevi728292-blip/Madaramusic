from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.decorators.admins import gate, need_active

LOOP_NAMES = {"off": "off", "song": "track", "track": "track", "queue": "queue", "all": "queue"}


def register(ctx):
    player = ctx.player

    @ctx.command("loop")
    async def loop(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        parts = (message.text or "").split(None, 1)
        q = player.queue(message.chat.id)
        if len(parts) > 1:
            mode = LOOP_NAMES.get(parts[1].strip().lower())
            if mode is None:
                return await message.reply_text("Use <code>/loop</code>, <code>/loop off</code>, <code>/loop song</code> or <code>/loop queue</code>.")
            q.loop = mode
        else:
            q.cycle_loop()
        await message.reply_text(f"🔁 Loop: <b>{text.LOOP_LABEL[q.loop]}</b>")

    @ctx.command("shuffle")
    async def shuffle(client, message):
        if not await gate(ctx, message) or not await need_active(ctx, message):
            return
        ok = player.queue(message.chat.id).shuffle()
        await message.reply_text("🔀 Shuffled the queue." if ok else "Add at least two songs to the queue first.")
