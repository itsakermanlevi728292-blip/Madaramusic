from __future__ import annotations

import logging

from SHUBHMUSIC.platforms.Youtube import APIError, DailyLimitReached, InvalidAPIKey, NotFound
from SHUBHMUSIC.core.context import classify, find_url
from SHUBHMUSIC.utils.exceptions import AssistantError, BotError
from SHUBHMUSIC.core.player import ChatLimitReached, QueueFull
from SHUBHMUSIC.utils import formatters as text
from SHUBHMUSIC.utils.formatters import esc

log = logging.getLogger("SHUBHMUSIC.play")

USAGE = (
    "🎵 <b>What should I play?</b>\n\n"
    "<code>/play song name</code>\n"
    "<code>/play https://youtu.be/…</code>\n"
    "<code>/play</code> as a reply to a message with a link"
)


def request_text(message) -> str:
    """The song request: text after the command, else the replied-to message."""
    parts = (message.text or message.caption or "").split(None, 1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if arg:
        return arg
    rep = getattr(message, "reply_to_message", None)
    if rep is not None:
        return (rep.text or rep.caption or "").strip()
    return ""


def explain(e: Exception) -> str:
    """One friendly sentence for anything that can go wrong while resolving a request."""
    if isinstance(e, DailyLimitReached):
        return text.limit_message(e.retry_after)
    if isinstance(e, InvalidAPIKey):
        return "⚠️ " + esc(e.message)
    if isinstance(e, NotFound):
        return "🔍 I could not find that. Try the artist and the song name, or a YouTube link."
    if isinstance(e, APIError):
        return "⚠️ " + esc(e.message)
    if isinstance(e, BotError):
        return "⚠️ " + esc(str(e))
    return "⚠️ Something went wrong. Please try again."


def register(ctx):
    player, api, cfg = ctx.player, ctx.api, ctx.cfg

    async def run(client, message, *, video: bool, force: bool):
        chat_id = message.chat.id
        if not await ctx.require(message, "play"):
            return
        if force and not await ctx.can(chat_id, message.from_user, "control", sender_chat=getattr(message, "sender_chat", None)):
            return await message.reply_text("👮 Only admins can use force-play.")
        query = request_text(message)
        if not query:
            return await message.reply_text(USAGE)
        kind = classify(query)
        if kind == "foreign":
            return await message.reply_text(
                "🔗 I can play <b>YouTube links</b> and song names. That link is from another site, "
                "so send the song name instead."
            )
        status = await message.reply_text("🔎 Searching…")
        user = message.from_user
        name = (user.first_name if user else "Anonymous admin") or "Someone"
        try:
            if kind == "playlist":
                title, tracks = await api.playlist(find_url(query), cfg.playlist_import_limit)
                if not tracks:
                    raise NotFound("empty playlist", "not_found", 404)
            else:
                tracks = [await api.track(find_url(query) if kind == "video" else query)]
                title = ""
            await ctx.assistants.ensure_present(chat_id)
            res = await player.add(chat_id, tracks, user_id=user.id if user else 0, user_name=name, video=video, force=force)
        except AssistantError as e:
            return await status.edit_text("⚠️ " + esc(str(e)))
        except (ChatLimitReached, QueueFull) as e:
            return await status.edit_text("⚠️ " + esc(str(e)))
        except Exception as e:
            if not isinstance(e, (APIError, BotError)):
                log.exception("play failed")
            return await status.edit_text(explain(e))
        if res.started:
            suffix = f"\n📂 Playlist <b>{esc(title)}</b>: {res.added} songs queued." if kind == "playlist" and res.added > 1 else ""
            try:
                if suffix:
                    await status.edit_text(suffix.strip())
                else:
                    await status.delete()
            except Exception:
                pass
        else:
            await status.edit_text(text.added(res.first, res.position, res.added, res.dropped))

    @ctx.command(["play", "p"])
    async def play(client, message):
        await run(client, message, video=False, force=False)

    @ctx.command(["vplay", "vp"])
    async def vplay(client, message):
        await run(client, message, video=True, force=False)

    @ctx.command(["playforce", "pf"])
    async def playforce(client, message):
        await run(client, message, video=False, force=True)

    @ctx.command(["vplayforce", "vpf"])
    async def vplayforce(client, message):
        await run(client, message, video=True, force=True)
