from __future__ import annotations

import logging
import secrets
import time


from SHUBHMUSIC.platforms.Youtube import APIError
from SHUBHMUSIC.utils.exceptions import AssistantError, BotError
from SHUBHMUSIC.core.player import ChatLimitReached, QueueFull
from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.inline.song import search_markup
from SHUBHMUSIC.utils.formatters import esc, fmt_time
from SHUBHMUSIC.plugins.play.play import explain, request_text

log = logging.getLogger("SHUBHMUSIC.search")
SEARCH_TTL = 600


def register(ctx):
    api, cfg, player = ctx.api, ctx.cfg, ctx.player

    def stash(user_id: int, tracks) -> str:
        now = time.time()
        for k in [k for k, v in ctx.search_cache.items() if v[2] < now]:
            ctx.search_cache.pop(k, None)
        token = secrets.token_hex(4)
        ctx.search_cache[token] = (user_id, tracks, now + SEARCH_TTL)
        return token

    @ctx.command(["search", "find"])
    async def search_cmd(client, message):
        if not await ctx.require(message, "play"):
            return
        query = request_text(message)
        if not query:
            return await message.reply_text("Use <code>/search song name</code> and I'll show the top results.")
        try:
            tracks = (await api.search(query, 5))[:5]
        except Exception as e:
            return await message.reply_text(explain(e))
        if not tracks:
            return await message.reply_text("🔍 No results. Try different words.")
        user = message.from_user
        token = stash(user.id if user else 0, tracks)
        lines = [f"🔎 <b>Results for</b> {esc(query)}\n"]
        for i, t in enumerate(tracks, 1):
            lines.append(f"<b>{i}.</b> {esc(text.short(t.title, 55))}\n     {esc(t.channel)} • <code>{fmt_time(t.duration)}</code>")
        await message.reply_text("\n".join(lines), reply_markup=search_markup(token, tracks))

    @ctx.callback("sr")
    async def search_cb(client, query):
        _, token, idx = query.data.split(":", 2)
        entry = ctx.search_cache.get(token)
        if entry is None or entry[2] < time.time():
            return await query.answer("This search expired. Search again.", show_alert=True)
        owner_id, tracks, _ = entry
        if query.from_user.id != owner_id:
            return await query.answer("Only the person who searched can pick.", show_alert=True)
        if idx == "x":
            ctx.search_cache.pop(token, None)
            await query.message.delete()
            return await query.answer()
        chat = query.message.chat
        if not await ctx.can(chat.id, query.from_user, "play"):
            return await query.answer("👮 Only admins can add songs here.", show_alert=True)
        track = tracks[int(idx)]
        ctx.search_cache.pop(token, None)
        await query.answer("Adding…")
        try:
            await ctx.assistants.ensure_present(chat.id)
            res = await player.add(chat.id, [track], user_id=query.from_user.id, user_name=query.from_user.first_name or "Someone")
        except (AssistantError, ChatLimitReached, QueueFull) as e:
            return await query.message.edit_text("⚠️ " + esc(str(e)))
        except Exception as e:
            if not isinstance(e, (APIError, BotError)):
                log.exception("search pick failed")
            return await query.message.edit_text(explain(e))
        if res.started:
            await query.message.delete()
        else:
            await query.message.edit_text(text.added(res.first, res.position, res.added, res.dropped))
