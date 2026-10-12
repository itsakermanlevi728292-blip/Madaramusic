from __future__ import annotations

from SHUBHMUSIC.utils.exceptions import AssistantError, BotError
from SHUBHMUSIC.core.player import ChatLimitReached, QueueFull
from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.inline.playlist import playlist_markup
from SHUBHMUSIC.utils.formatters import esc, fmt_time


def register(ctx):
    store, player = ctx.store, ctx.player

    def render(tracks) -> str:
        if not tracks:
            return "❤️ <b>Your playlist is empty.</b>\nPlay a song, then tap <b>❤️ Save</b> on the player or send /like."
        lines = ["❤️ <b>Your playlist</b>\n"]
        for i, t in enumerate(tracks[:30], 1):
            lines.append(f"<b>{i}.</b> {esc(text.short(t.title, 48))}  <code>{fmt_time(t.duration)}</code>")
        if len(tracks) > 30:
            lines.append(f"…and {len(tracks) - 30} more")
        lines.append(f"\n{len(tracks)} songs • remove one with <code>/delsong n</code>")
        return "\n".join(lines)

    @ctx.command(["like", "save", "fav"])
    async def like(client, message):
        q = player.queues.get(message.chat.id)
        if q is None or q.current is None:
            return await message.reply_text("Play a song first, then /like saves it to your playlist.")
        user = message.from_user
        if user is None:
            return await message.reply_text("Anonymous admins cannot have a playlist. Send this from your own account.")
        res = await store.playlist_add(user.id, q.current)
        await message.reply_text({"added": "❤️ Saved to your playlist.", "exists": "That song is already in your playlist.",
                                  "full": "Your playlist is full (100 songs). Remove some with /delsong."}[res])

    @ctx.command(["playlist", "pl", "mylist"], group_only=False)
    async def playlist(client, message):
        user = message.from_user
        if user is None:
            return
        tracks = await store.playlist_list(user.id)
        await message.reply_text(render(tracks), reply_markup=playlist_markup(len(tracks)))

    @ctx.command("delsong", group_only=False)
    async def delsong(client, message):
        user = message.from_user
        parts = (message.text or "").split(None, 1)
        if user is None or len(parts) < 2 or not parts[1].strip().isdigit():
            return await message.reply_text("Use <code>/delsong 2</code> to remove song number 2 from your playlist.")
        ok = await store.playlist_remove(user.id, int(parts[1]))
        await message.reply_text("🗑 Removed." if ok else "There is no song with that number in your playlist.")

    @ctx.callback("pm")
    async def playlist_cb(client, query):
        action = query.data.split(":", 1)[1]
        user, msg = query.from_user, query.message
        if action == "close":
            await msg.delete()
            return await query.answer()
        if action == "clear":
            n = await store.playlist_clear(user.id)
            await msg.edit_text(render([]), reply_markup=playlist_markup(0))
            return await query.answer(f"Removed {n} songs")
        if action == "play":
            chat = msg.chat
            if chat.type.name not in ("GROUP", "SUPERGROUP"):
                return await query.answer("Open this in a group to play it in the voice chat.", show_alert=True)
            if not await ctx.can(chat.id, user, "play"):
                return await query.answer("👮 Only admins can add songs here.", show_alert=True)
            tracks = await store.playlist_list(user.id)
            if not tracks:
                return await query.answer("Your playlist is empty.", show_alert=True)
            await query.answer("Adding your playlist…")
            try:
                await ctx.assistants.ensure_present(chat.id)
                res = await player.add(chat.id, tracks, user_id=user.id, user_name=user.first_name or "Someone")
            except (AssistantError, ChatLimitReached, QueueFull, BotError) as e:
                return await ctx.say(chat.id, "⚠️ " + esc(str(e)))
            if not res.started:
                await ctx.say(chat.id, text.added(res.first, res.position, res.added, res.dropped))
