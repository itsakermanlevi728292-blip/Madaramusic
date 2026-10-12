from __future__ import annotations

import asyncio
import logging
import os
import secrets
import tempfile
import time

import httpx
from pyrogram import enums

from ..api import APIError
from ..errors import AssistantError, BotError
from ..player import ChatLimitReached, QueueFull
from ..ui import keyboards, text
from ..ui.text import esc, fmt_time
from .play import explain, request_text

log = logging.getLogger("bot.search")
SEARCH_TTL = 600


async def to_mp3(src: str, dst: str, *, bitrate: str = "160k") -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-map_metadata", "-1",
        "-acodec", "libmp3lame", "-b:a", bitrate, dst,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0 or not os.path.exists(dst):
        raise BotError("Could not convert that song to MP3.")


async def fetch_file(url: str, dst: str, max_bytes: int, http: httpx.AsyncClient) -> None:
    total = 0
    async with http.stream("GET", url) as r:
        if r.status_code != 200:
            raise BotError("The music server could not deliver that song right now.")
        with open(dst, "wb") as f:
            async for chunk in r.aiter_bytes(262144):
                total += len(chunk)
                if total > max_bytes:
                    raise BotError("That song is too large to send as a file.")
                f.write(chunk)


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
        await message.reply_text("\n".join(lines), reply_markup=keyboards.search_results(token, tracks))

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

    @ctx.command(["song", "download", "mp3"], group_only=False)
    async def song(client, message):
        query = request_text(message)
        if not query:
            return await message.reply_text("Use <code>/song name</code> and I'll send it as an MP3 file.")
        status = await message.reply_text("⬇️ Getting your song…")
        tmpdir = tempfile.mkdtemp(prefix="song_")
        try:
            track = await api.track(query)
            if track.duration and track.duration > 20 * 60:
                return await status.edit_text("⚠️ Songs longer than 20 minutes can't be sent as files.")
            stream = await api.play(track.id)  # counts as one song on the API plan
            raw, out = os.path.join(tmpdir, "in.bin"), os.path.join(tmpdir, "song.mp3")
            await fetch_file(stream.url, raw, cfg.song_max_mb * 1024 * 1024, api.http)
            await to_mp3(raw, out)
            if os.path.getsize(out) > cfg.song_max_mb * 1024 * 1024:
                return await status.edit_text("⚠️ That file is too large to send.")
            await status.edit_text("⬆️ Uploading…")
            await client.send_audio(
                message.chat.id, out, caption=f"🎧 {esc(track.title)}", title=track.title[:64], performer=(track.channel or "")[:64],
                duration=track.duration, reply_to_message_id=message.id, parse_mode=enums.ParseMode.HTML,
            )
            await status.delete()
        except Exception as e:
            if not isinstance(e, (APIError, BotError)):
                log.exception("song download failed")
            await status.edit_text(explain(e))
        finally:
            for f in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, f))
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
