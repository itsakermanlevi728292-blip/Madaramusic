"""Buttons under the now-playing card and the queue pager."""

import logging

from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.exceptions import BotError
from SHUBHMUSIC.utils.formatters import fmt_time
from SHUBHMUSIC.utils.inline.play import SEEK_STEP, VOLUME_STEP, player_markup
from SHUBHMUSIC.utils.inline.queue import queue_markup

log = logging.getLogger("SHUBHMUSIC.callback")


def register(ctx):
    player, store = ctx.player, ctx.store

    async def refresh(query, q):
        try:
            if q.current is None:
                return
            body, markup = text.now_playing(q, ctx.cfg.bot_name), player_markup(q)
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
                step = VOLUME_STEP if action == "vup" else -VOLUME_STEP
                v = await player.set_volume(chat_id, q.volume + step)
                await query.answer(f"🔊 {v}%")
            elif action in ("fwd", "back"):
                step = SEEK_STEP if action == "fwd" else -SEEK_STEP
                target = await player.seek(chat_id, delta=step)
                await query.answer(f"⏩ {fmt_time(target)}" if target is not None else "Can't jump there")
            elif action == "save":
                res = await store.playlist_add(user.id, q.current)
                await query.answer({"added": "❤️ Saved to your playlist", "exists": "Already in your playlist",
                                    "full": "Your playlist is full (100 songs)"}[res], show_alert=res == "full")
                return
            elif action == "queue":
                body, pages = text.queue_page(q, 0)
                await query.message.reply_text(body, reply_markup=queue_markup(0, pages) if pages > 1 else None)
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
        await query.message.edit_text(body, reply_markup=queue_markup(page, pages))
        await query.answer()
