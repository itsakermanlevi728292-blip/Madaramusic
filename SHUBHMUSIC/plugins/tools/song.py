from __future__ import annotations

import asyncio
import logging
import os
import tempfile

import httpx
from pyrogram import enums

from SHUBHMUSIC.platforms.Youtube import APIError
from SHUBHMUSIC.plugins.play.play import explain, request_text
from SHUBHMUSIC.utils.exceptions import BotError
from SHUBHMUSIC.utils.formatters import esc

log = logging.getLogger("SHUBHMUSIC.song")


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
    api, cfg = ctx.api, ctx.cfg

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
