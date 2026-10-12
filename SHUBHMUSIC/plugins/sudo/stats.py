import time

from SHUBHMUSIC.utils.decorators.sudo import power
from SHUBHMUSIC.utils.formatters import esc, fmt_time
from SHUBHMUSIC.platforms.Youtube import APIError


def register(ctx):
    store = ctx.store

    @ctx.command("stats", group_only=False)
    async def stats(client, message):
        if not await power(ctx, message):
            return
        c = await store.counts()
        up = int(time.time() - ctx.started_at)
        await message.reply_text(
            "📊 <b>Bot stats</b>\n"
            f"<blockquote>Groups: <code>{c['chats']}</code>\n"
            f"Users: <code>{c['users']}</code>\n"
            f"Saved playlist songs: <code>{c['playlist_songs']}</code>\n"
            f"Playing right now: <code>{len(ctx.player.active_chats())}</code> group(s)\n"
            f"Assistants: <code>{len(ctx.assistants.userbots)}</code>\n"
            f"Uptime: <code>{fmt_time(up)}</code></blockquote>"
        )

    @ctx.command("usage", group_only=False)
    async def usage(client, message):
        if not await power(ctx, message):
            return
        try:
            u = await ctx.api.usage()
        except APIError as e:
            return await message.reply_text(f"⚠️ Could not read the API plan: {esc(str(e))}")
        bar_used = min(1.0, u.used_today / u.daily_limit) if u.daily_limit else 0
        filled = int(bar_used * 14)
        expires = f"\nPlan ends: <code>{esc(u.plan_expires_at)}</code>" if u.plan_expires_at else ""
        await message.reply_text(
            "🔑 <b>API usage today</b>\n"
            f"Plan: <b>{esc(u.plan)}</b>{expires}\n"
            f"Used: <code>{u.used_today}</code> / <code>{u.daily_limit}</code>\n"
            f"Left: <code>{u.remaining_today}</code>\n"
            f"<code>{'█' * filled}{'░' * (14 - filled)}</code>"
        )
