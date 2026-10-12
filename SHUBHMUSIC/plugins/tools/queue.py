from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.decorators.admins import gate, need_active
from SHUBHMUSIC.utils.formatters import esc
from SHUBHMUSIC.utils.inline.queue import queue_markup


def register(ctx):
    player = ctx.player

    @ctx.command(["queue", "q"])
    async def queue_cmd(client, message):
        q = player.queue(message.chat.id)
        if q.current is None:
            return await message.reply_text("The queue is empty. Add songs with /play.")
        body, pages = text.queue_page(q, 0)
        await message.reply_text(body, reply_markup=queue_markup(0, pages) if pages > 1 else None)

    @ctx.command(["now", "np", "player", "playing"])
    async def now(client, message):
        q = await need_active(ctx, message)
        if q is None:
            return
        await ctx.player.notifier.now_playing(message.chat.id, q)

    @ctx.command("remove")
    async def remove(client, message):
        if not await gate(ctx, message):
            return
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            return await message.reply_text("Use <code>/remove 3</code> to remove song number 3 from the queue.")
        gone = player.queue(message.chat.id).remove(int(parts[1]))
        await message.reply_text(f"🗑 Removed <b>{esc(text.short(gone.title, 50))}</b>." if gone else "There is no song with that number.")

    @ctx.command("move")
    async def move(client, message):
        if not await gate(ctx, message):
            return
        args = (message.text or "").split()[1:]
        if len(args) != 2 or not all(a.isdigit() for a in args):
            return await message.reply_text("Use <code>/move 4 1</code> to move song 4 to the front.")
        ok = player.queue(message.chat.id).move(int(args[0]), int(args[1]))
        await message.reply_text("✅ Moved." if ok else "Those numbers are not in the queue.")

    @ctx.command("clear")
    async def clear(client, message):
        if not await gate(ctx, message):
            return
        n = player.queue(message.chat.id).clear()
        await message.reply_text(f"🧹 Removed {n} songs from the queue." if n else "The queue is already empty.")
