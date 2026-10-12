"""Entry point: `python -m SHUBHMUSIC` (or `bash start`)."""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import config
from SHUBHMUSIC.logging import LOGGER, setup

COMMANDS = [
    ("play", "Play a song or add it to the queue"),
    ("vplay", "Play the video in the voice chat"),
    ("playforce", "Play now, ahead of the queue"),
    ("search", "Pick a song from the top results"),
    ("song", "Download a song as MP3"),
    ("pause", "Pause"),
    ("resume", "Resume"),
    ("skip", "Skip to the next song"),
    ("stop", "Stop and clear the queue"),
    ("seek", "Jump forward or to a time"),
    ("loop", "Loop: off, song, queue"),
    ("shuffle", "Shuffle the queue"),
    ("volume", "Set the volume"),
    ("queue", "Show the queue"),
    ("now", "Show what is playing"),
    ("like", "Save this song to your playlist"),
    ("playlist", "Your saved playlist"),
    ("settings", "Group settings (admins)"),
    ("help", "All commands"),
    ("ping", "Check speed"),
]


async def start_health_server(port: int):
    """Tiny HTTP endpoint so hosts like Railway/Render can see the bot is alive."""
    from aiohttp import web

    async def ok(_):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    LOGGER("SHUBHMUSIC").info("health server on :%s", port)
    return runner


async def init(cfg: config.Config) -> None:
    from pyrogram.types import BotCommand
    from pytgcalls import PyTgCalls

    from SHUBHMUSIC.core.bot import build_bot
    from SHUBHMUSIC.core.call import TgCallsBackend
    from SHUBHMUSIC.core.context import Ctx
    from SHUBHMUSIC.core.notifier import TelegramNotifier
    from SHUBHMUSIC.core.player import Player
    from SHUBHMUSIC.core.userbot import AssistantManager, build_userbots
    from SHUBHMUSIC.platforms.Youtube import APIError, InvalidAPIKey, YouTubeAPI
    from SHUBHMUSIC.plugins import register_all
    from SHUBHMUSIC.utils.database import Store
    from SHUBHMUSIC.utils.thumbnails import CardMaker

    log = LOGGER("SHUBHMUSIC")
    os.makedirs(cfg.data_dir, exist_ok=True)
    store = Store(os.path.join(cfg.data_dir, "bot.db"), cfg.timezone)
    await store.open()
    api = YouTubeAPI(cfg.api_url, cfg.api_key)

    # Fail early and clearly if the API address or key is wrong.
    try:
        usage = await api.usage()
        log.info("API ok: plan=%s, %s/%s used today", usage.plan, usage.used_today, usage.daily_limit)
    except InvalidAPIKey:
        raise config.ConfigError("[config] The API rejected API_KEY. Copy a fresh key from your API's /portal page.")
    except APIError as e:
        log.warning("Could not reach the API at start-up (%s). The bot will keep trying.", e)

    app = build_bot(cfg)
    userbots = build_userbots(cfg)
    calls = [PyTgCalls(u) for u in userbots]
    backend = TgCallsBackend(calls)
    cards = CardMaker(cfg.bot_name)
    assistants = AssistantManager(app, userbots)

    ctx = Ctx(cfg=cfg, app=app, api=api, store=store, player=None, assistants=assistants, cards=cards)
    player = Player(cfg, api, backend, store, TelegramNotifier(ctx))
    ctx.player = player
    backend.attach(player)
    register_all(ctx)

    await app.start()
    for u in userbots:
        await u.start()
    for c in calls:
        await c.start()
    me = await app.get_me()
    ctx.bot_username = me.username or ""
    try:
        await app.set_bot_commands([BotCommand(n, d) for n, d in COMMANDS])
    except Exception:
        log.warning("could not set the command menu", exc_info=True)
    player.start_housekeeping()
    runner = await start_health_server(cfg.health_port) if cfg.health_port else None
    log.info("%s is online as @%s with %d assistant(s)", cfg.bot_name, ctx.bot_username, len(userbots))
    await ctx.log_event(f"✅ <b>{cfg.bot_name}</b> is online.")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()

    log.info("shutting down…")
    await player.shutdown()
    for chat_id in player.active_chats():
        try:
            await backend.stop(chat_id)
        except Exception:
            pass
    if runner:
        await runner.cleanup()
    for u in userbots:
        try:
            await u.stop()
        except Exception:
            pass
    try:
        await app.stop()
    except Exception:
        pass
    await cards.close()
    await api.close()
    await store.close()


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    setup()
    try:
        cfg = config.Config.from_env()
        asyncio.run(init(cfg))
    except config.ConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
