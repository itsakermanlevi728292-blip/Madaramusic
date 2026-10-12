from __future__ import annotations

import time

from pyrogram import enums

from ..ui import keyboards
from ..ui.text import esc

HELP = {
    "play": (
        "🎵 <b>Play music</b>\n\n"
        "/play <i>song name or YouTube link</i>: play or queue a song\n"
        "/play <i>playlist link</i>: queue a whole YouTube playlist\n"
        "/vplay <i>name or link</i>: play the video in the voice chat\n"
        "/playforce <i>name</i>: play right now, ahead of the queue\n"
        "/search <i>name</i>: pick from the top results\n"
        "/song <i>name</i>: download a song as an MP3 file\n\n"
        "You can also reply to a message that contains a link with /play."
    ),
    "ctrl": (
        "🎛 <b>Controls</b>\n\n"
        "/pause • /resume • /skip • /stop\n"
        "/seek <i>1:30</i> or <i>+30</i> • /seekback <i>15</i>\n"
        "/loop (off → song → queue) • /shuffle\n"
        "/volume <i>1-200</i> • /now • /player\n\n"
        "Every action is also a button on the player card."
    ),
    "list": (
        "📜 <b>Queue &amp; playlists</b>\n\n"
        "/queue: see what is coming up\n"
        "/remove <i>n</i> • /move <i>from to</i> • /clear\n"
        "/like: save the current song to <b>your</b> playlist\n"
        "/playlist: open your playlist (play it, remove songs, clear it)"
    ),
    "admin": (
        "👮 <b>Admin</b>\n\n"
        "/settings: who can play and who can control\n"
        "/auth <i>(reply or @user)</i>: let someone control the player\n"
        "/unauth • /authusers\n"
        "/reload: refresh the admin list"
    ),
    "owner": (
        "👑 <b>Owner</b>\n\n"
        "/stats • /usage: bot and API quota\n"
        "/broadcast <i>text</i> • /ban • /unban • /sudo • /unsudo"
    ),
}

HOW = (
    "⚙️ <b>How to set me up</b>\n\n"
    "1. Add me to your group and make me an <b>admin</b> (Invite users, Manage voice chats).\n"
    "2. Start a voice chat in the group.\n"
    "3. Send /play and a song name. My assistant account joins automatically.\n\n"
    "Nothing to configure: just add, start the voice chat and play."
)


def register(ctx):
    cfg = ctx.cfg

    def start_text() -> str:
        return (
            f"🎧 <b>{esc(cfg.bot_name)}</b>\n\n"
            "I play music and videos in your group's voice chat: fast, with a queue, "
            "loop, seek, volume and personal playlists.\n\n"
            "Add me to a group, start a voice chat and send <code>/play song name</code>."
        )

    @ctx.command("start", group_only=False)
    async def start(client, message):
        if message.chat.type != enums.ChatType.PRIVATE:
            return await message.reply_text("🎧 I'm ready. Start a voice chat, then send /play and a song name.")
        markup = keyboards.start(ctx.bot_username, cfg.support_chat, cfg.support_channel)
        if cfg.start_image_url:
            try:
                return await message.reply_photo(cfg.start_image_url, caption=start_text(), reply_markup=markup,
                                                 parse_mode=enums.ParseMode.HTML)
            except Exception:
                pass
        await message.reply_text(start_text(), reply_markup=markup)

    @ctx.command("help", group_only=False)
    async def help_cmd(client, message):
        await message.reply_text("📖 <b>Commands</b>\nPick a topic:", reply_markup=keyboards.help_main())

    @ctx.command("ping", group_only=False)
    async def ping(client, message):
        t0 = time.perf_counter()
        sent = await message.reply_text("🏓 …")
        tg_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        ok = await ctx.api.health()
        api_ms = (time.perf_counter() - t1) * 1000
        up = int(time.time() - ctx.started_at)
        d, rem = divmod(up, 86400)
        h, rem = divmod(rem, 3600)
        await sent.edit_text(
            f"🏓 <b>Pong</b>\nTelegram: <code>{tg_ms:.0f} ms</code>\n"
            f"Music server: {'🟢' if ok else '🔴'} <code>{api_ms:.0f} ms</code>\n"
            f"Uptime: <code>{d}d {h}h {rem // 60}m</code>"
        )

    @ctx.callback("hp")
    async def help_cb(client, query):
        action = query.data.split(":", 1)[1]
        msg = query.message
        if action == "close":
            await msg.delete()
            return await query.answer()
        if action == "home":
            body, markup = start_text(), keyboards.start(ctx.bot_username, cfg.support_chat, cfg.support_channel)
        elif action == "main":
            body, markup = "📖 <b>Commands</b>\nPick a topic:", keyboards.help_main()
        elif action == "how":
            body, markup = HOW, keyboards.help_back()
        elif action in HELP:
            body, markup = HELP[action], keyboards.help_back()
        else:
            return await query.answer()
        if msg.photo:
            await msg.edit_caption(body, reply_markup=markup)
        else:
            await msg.edit_text(body, reply_markup=markup)
        await query.answer()
