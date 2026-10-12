from __future__ import annotations

from pyrogram.types import InlineKeyboardButton as B
from pyrogram.types import InlineKeyboardMarkup as M

from ..queue import ChatQueue

SEEK_STEP = 15
VOLUME_STEP = 10


def player(q: ChatQueue) -> M:
    pp = B("▶️ Resume" if q.paused else "⏸ Pause", callback_data="pl:pause")
    loop_icon = {"off": "🔁", "track": "🔂", "queue": "🔁"}[q.loop]
    loop_text = {"off": "Loop", "track": "Loop: song", "queue": "Loop: all"}[q.loop]
    return M([
        [pp, B("⏭ Skip", callback_data="pl:skip"), B("⏹ Stop", callback_data="pl:stop")],
        [B(f"{loop_icon} {loop_text}", callback_data="pl:loop"), B("🔀 Shuffle", callback_data="pl:shuffle"),
         B("❤️ Save", callback_data="pl:save")],
        [B(f"⏪ {SEEK_STEP}s", callback_data="pl:back"), B(f"🔉 {max(1, q.volume - VOLUME_STEP)}", callback_data="pl:vdown"),
         B(f"🔊 {min(200, q.volume + VOLUME_STEP)}", callback_data="pl:vup"), B(f"{SEEK_STEP}s ⏩", callback_data="pl:fwd")],
        [B("📜 Queue", callback_data="pl:queue"), B("🔄 Refresh", callback_data="pl:refresh"),
         B("✖️ Close", callback_data="pl:close")],
    ])


def queue_nav(page: int, pages: int) -> M:
    row = []
    if page > 0:
        row.append(B("◀️ Prev", callback_data=f"qu:{page - 1}"))
    row.append(B(f"{page + 1}/{pages}", callback_data="qu:noop"))
    if page < pages - 1:
        row.append(B("Next ▶️", callback_data=f"qu:{page + 1}"))
    return M([row, [B("⬅️ Back to player", callback_data="pl:refresh"), B("✖️ Close", callback_data="pl:close")]])


def search_results(token: str, tracks) -> M:
    rows = [[B(f"{i}. {t.title[:44]}", callback_data=f"sr:{token}:{i - 1}")] for i, t in enumerate(tracks, 1)]
    rows.append([B("✖️ Close", callback_data=f"sr:{token}:x")])
    return M(rows)


def start(bot_username: str, support_chat: str, support_channel: str) -> M:
    rows = [[B("➕ Add me to your group", url=f"https://t.me/{bot_username}?startgroup=true&admin=invite_users+manage_video_chats+delete_messages+pin_messages")],
            [B("📖 Commands", callback_data="hp:main"), B("⚙️ How it works", callback_data="hp:how")]]
    links = []
    if support_chat:
        links.append(B("💬 Support", url=support_chat))
    if support_channel:
        links.append(B("📣 Updates", url=support_channel))
    if links:
        rows.append(links)
    return M(rows)


HELP_SECTIONS = {
    "play": "🎵 Play",
    "ctrl": "🎛 Controls",
    "list": "📜 Queue & playlists",
    "admin": "👮 Admin",
    "owner": "👑 Owner",
}


def help_main() -> M:
    keys = list(HELP_SECTIONS)
    rows = [[B(HELP_SECTIONS[k], callback_data=f"hp:{k}") for k in keys[i:i + 2]] for i in range(0, len(keys), 2)]
    rows.append([B("🏠 Home", callback_data="hp:home"), B("✖️ Close", callback_data="hp:close")])
    return M(rows)


def help_back() -> M:
    return M([[B("⬅️ Back", callback_data="hp:main"), B("✖️ Close", callback_data="hp:close")]])


def settings(s: dict) -> M:
    return M([
        [B(f"🎵 Who can play: {'everyone' if s['play_mode'] == 'everyone' else 'admins only'}", callback_data="st:play")],
        [B(f"🎛 Who can control: {'everyone' if s['control_mode'] == 'everyone' else 'admins only'}", callback_data="st:control")],
        [B(f"🧹 Delete commands: {'on' if s['clean_commands'] else 'off'}", callback_data="st:clean")],
        [B("✖️ Close", callback_data="st:close")],
    ])


def playlist_menu(count: int) -> M:
    rows = []
    if count:
        rows.append([B("▶️ Play all", callback_data="pm:play"), B("🗑 Clear", callback_data="pm:clear")])
    rows.append([B("✖️ Close", callback_data="pm:close")])
    return M(rows)
