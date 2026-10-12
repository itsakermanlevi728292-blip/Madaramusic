from __future__ import annotations

import logging

from pyrogram import enums

from ..errors import BotError
from ..queue import LOOP_CYCLE
from ..ui import keyboards, text
from ..ui.text import esc, fmt_time, parse_time

log = logging.getLogger("bot.controls")

LOOP_NAMES = {"off": "off", "song": "track", "track": "track", "queue": "queue", "all": "queue"}


def register(ctx):
    player, store = ctx.player, ctx.store

    async def need_active(message):
        q = player.queues.get(message.chat.id)
        if q is None or q.current is None:
            await message.reply_text("Nothing is playing right now. Start with /play.")
            return None
        return q

    async def gate(message) -> bool:
        return await ctx.require(message, "control")

    # ── playback commands ─────────────────────────────────────────────────
    @ctx.command("pause")
    async def pause(client, message):
        if not await gate(message) or not await need_active(message):
            return
        ok = await player.pause(message.chat.id)
        await message.reply_text("⏸ Paused." if ok else "It is already paused.")

    @ctx.command("resume")
    async def resume(client, message):
        if not await gate(message) or not await need_active(message):
            return
        ok = await player.resume(message.chat.id)
        await message.reply_text("▶️ Resumed." if ok else "It is not paused.")

    @ctx.command(["skip", "next"])
    async def skip(client, message):
        if not await gate(message) or not await need_active(message):
            return
        res = await player.skip(message.chat.id)
        if res and res[1] is None:
            return  # the notifier already said the queue finished
        if res:
            await message.reply_text(f"⏭ Skipped <b>{esc(text.short(res[0].title, 50))}</b>.")

    @ctx.command(["stop", "end"])
    async def stop(client, message):
        if not await gate(message):
            return
        ok = await player.stop(message.chat.id)
        await message.reply_text("⏹ Stopped and cleared the queue." if ok else "Nothing is playing right now.")

    async def do_seek(message, sign: int):
        if not await gate(message) or not await need_active(message):
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

    @ctx.command("loop")
    async def loop(client, message):
        if not await gate(message) or not await need_active(message):
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
        if not await gate(message) or not await need_active(message):
            return
        ok = player.queue(message.chat.id).shuffle()
        await message.reply_text("🔀 Shuffled the queue." if ok else "Add at least two songs to the queue first.")

    @ctx.command(["volume", "vol"])
    async def volume(client, message):
        if not await gate(message) or not await need_active(message):
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

    # ── queue editing ─────────────────────────────────────────────────────
    @ctx.command("remove")
    async def remove(client, message):
        if not await gate(message):
            return
        parts = (message.text or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            return await message.reply_text("Use <code>/remove 3</code> to remove song number 3 from the queue.")
        gone = player.queue(message.chat.id).remove(int(parts[1]))
        await message.reply_text(f"🗑 Removed <b>{esc(text.short(gone.title, 50))}</b>." if gone else "There is no song with that number.")

    @ctx.command("move")
    async def move(client, message):
        if not await gate(message):
            return
        args = (message.text or "").split()[1:]
        if len(args) != 2 or not all(a.isdigit() for a in args):
            return await message.reply_text("Use <code>/move 4 1</code> to move song 4 to the front.")
        ok = player.queue(message.chat.id).move(int(args[0]), int(args[1]))
        await message.reply_text("✅ Moved." if ok else "Those numbers are not in the queue.")

    @ctx.command("clear")
    async def clear(client, message):
        if not await gate(message):
            return
        n = player.queue(message.chat.id).clear()
        await message.reply_text(f"🧹 Removed {n} songs from the queue." if n else "The queue is already empty.")

    # ── information (anyone) ──────────────────────────────────────────────
    @ctx.command(["queue", "q"])
    async def queue_cmd(client, message):
        q = player.queue(message.chat.id)
        if q.current is None:
            return await message.reply_text("The queue is empty. Add songs with /play.")
        body, pages = text.queue_page(q, 0)
        await message.reply_text("📜 <b>Queue</b>\n\n" + body, reply_markup=keyboards.queue_nav(0, pages) if pages > 1 else None)

    @ctx.command(["now", "np", "player", "playing"])
    async def now(client, message):
        q = await need_active(message)
        if q is None:
            return
        await ctx.player.notifier.now_playing(message.chat.id, q)

    # ── buttons on the player card ────────────────────────────────────────
    async def refresh(query, q):
        try:
            if q.current is None:
                return
            body, markup = text.now_playing(q, ctx.cfg.bot_name), keyboards.player(q)
            if query.message.photo:
                await query.message.edit_caption(body, reply_markup=markup)
            else:
                await query.message.edit_text(body, reply_markup=markup)
        except Exception as e:  # "message is not modified" is normal when nothing changed
            if "MESSAGE_NOT_MODIFIED" not in str(e).upper():
                log.debug("refresh failed: %s", e)

    @ctx.callback("pl")
    async def player_cb(client, query):
        chat_id = query.message.chat.id
        action = query.data.split(":", 1)[1]
        user = query.from_user
        need = None if action in ("refresh", "queue", "save") else "control"  # anyone may look or save
        if need and not await ctx.can(chat_id, user, need):
            return await query.answer("👮 Only admins (or authorised users) can use these buttons.", show_alert=True)
        q = player.queues.get(chat_id)
        if action == "close":
            await query.message.delete()
            if q is not None and q.last_message_id == query.message.id:
                q.last_message_id = None
            return await query.answer()
        if q is None or q.current is None:
            await query.answer("Nothing is playing right now.", show_alert=True)
            return
        try:
            if action == "pause":
                await player.resume(chat_id) if q.paused else await player.pause(chat_id)
                await query.answer("▶️ Resumed" if not q.paused else "⏸ Paused")
            elif action == "skip":
                await query.answer("⏭ Skipping…")
                await player.skip(chat_id)
                return
            elif action == "stop":
                await player.stop(chat_id)
                await query.answer("⏹ Stopped")
                try:
                    await query.message.delete()
                except Exception:
                    pass
                return
            elif action == "loop":
                mode = await player.cycle_loop(chat_id)
                await query.answer(f"🔁 Loop: {text.LOOP_LABEL[mode]}")
            elif action == "shuffle":
                ok = q.shuffle()
                await query.answer("🔀 Shuffled" if ok else "Queue needs 2+ songs")
            elif action in ("vup", "vdown"):
                step = keyboards.VOLUME_STEP if action == "vup" else -keyboards.VOLUME_STEP
                v = await player.set_volume(chat_id, q.volume + step)
                await query.answer(f"🔊 {v}%")
            elif action in ("fwd", "back"):
                step = keyboards.SEEK_STEP if action == "fwd" else -keyboards.SEEK_STEP
                target = await player.seek(chat_id, delta=step)
                await query.answer(f"⏩ {fmt_time(target)}" if target is not None else "Can't jump there")
            elif action == "save":
                res = await store.playlist_add(user.id, q.current)
                await query.answer({"added": "❤️ Saved to your playlist", "exists": "Already in your playlist",
                                    "full": "Your playlist is full (100 songs)"}[res], show_alert=res == "full")
                return
            elif action == "queue":
                body, pages = text.queue_page(q, 0)
                await query.message.reply_text("📜 <b>Queue</b>\n\n" + body, reply_markup=keyboards.queue_nav(0, pages) if pages > 1 else None)
                return await query.answer()
            elif action == "refresh":
                await query.answer("🔄")
        except BotError as e:
            return await query.answer(str(e)[:190], show_alert=True)
        await refresh(query, q)

    @ctx.callback("qu")
    async def queue_cb(client, query):
        arg = query.data.split(":", 1)[1]
        if arg == "noop":
            return await query.answer()
        q = player.queues.get(query.message.chat.id)
        if q is None or q.current is None:
            return await query.answer("The queue is empty.", show_alert=True)
        body, pages = text.queue_page(q, int(arg))
        page = max(0, min(int(arg), pages - 1))
        await query.message.edit_text("📜 <b>Queue</b>\n\n" + body, reply_markup=keyboards.queue_nav(page, pages))
        await query.answer()
