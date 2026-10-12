"""Entry point: `python -m bot`."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from .config import Config, ConfigError

log = logging.getLogger("bot")

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
    log.info("health server on :%s", port)
    return runner


async def run(cfg: Config) -> None:
    from pyrogram import Client, enums
    from pyrogram.types import BotCommand
    from pytgcalls import PyTgCalls

    from .api import APIError, InvalidAPIKey, MusicAPI
    from .assistant import AssistantManager
    from .backend import TgCallsBackend
    from .context import Ctx
    from .handlers import register_all
    from .notifier import TelegramNotifier
    from .player import Player
    from .store import Store
    from .ui.card import CardMaker

    os.makedirs(cfg.data_dir, exist_ok=True)
    store = Store(os.path.join(cfg.data_dir, "bot.db"), cfg.timezone)
    await store.open()
    api = MusicAPI(cfg.api_url, cfg.api_key)

    # Fail early and clearly if the API address or key is wrong.
    try:
        usage = await api.usage()
        log.info("API ok: plan=%s, %s/%s used today", usage.plan, usage.used_today, usage.daily_limit)
    except InvalidAPIKey:
        raise ConfigError("[config] The API rejected API_KEY. Copy a fresh key from your API's /portal page.")
    except APIError as e:
        log.warning("Could not reach the API at start-up (%s). The bot will keep trying.", e)

    app = Client("bot", api_id=cfg.api_id, api_hash=cfg.api_hash, bot_token=cfg.bot_token,
                 workdir=cfg.data_dir, parse_mode=enums.ParseMode.HTML, max_concurrent_transmissions=4)
    userbots = [
        Client(f"assistant{i}", api_id=cfg.api_id, api_hash=cfg.api_hash, session_string=s,
               in_memory=True, no_updates=False, max_concurrent_transmissions=4)
        for i, s in enumerate(cfg.session_strings, 1)
    ]
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
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        cfg = Config.from_env()
    except ConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    try:
        asyncio.run(run(cfg))
    except ConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
