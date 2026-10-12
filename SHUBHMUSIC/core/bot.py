"""The bot account (talks to users)."""

from pyrogram import Client, enums


def build_bot(cfg) -> Client:
    return Client(
        "bot", api_id=cfg.api_id, api_hash=cfg.api_hash, bot_token=cfg.bot_token,
        workdir=cfg.data_dir, parse_mode=enums.ParseMode.HTML, max_concurrent_transmissions=4,
    )
