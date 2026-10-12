"""All the longer texts the bot shows (HTML). Short one-line replies live next to the code that sends them."""

from SHUBHMUSIC.utils.formatters import esc

HELP = {
    "play": (
        "🎵 <b>Play music</b>\n\n"
        "<blockquote>/play <i>song name or YouTube link</i>: play or queue a song\n"
        "/play <i>playlist link</i>: queue a whole YouTube playlist\n"
        "/vplay <i>name or link</i>: play the video in the voice chat\n"
        "/playforce <i>name</i>: play right now, ahead of the queue\n"
        "/search <i>name</i>: pick from the top results\n"
        "/song <i>name</i>: download a song as an MP3 file</blockquote>\n"
        "You can also reply to a message that contains a link with /play."
    ),
    "ctrl": (
        "🎛 <b>Controls</b>\n\n"
        "<blockquote>/pause • /resume • /skip • /stop\n"
        "/seek <i>1:30</i> or <i>+30</i> • /seekback <i>15</i>\n"
        "/loop (off → song → queue) • /shuffle\n"
        "/volume <i>1-200</i> • /now • /player</blockquote>\n"
        "Every action is also a coloured button on the player card."
    ),
    "list": (
        "📜 <b>Queue &amp; playlists</b>\n\n"
        "<blockquote>/queue: see what is coming up\n"
        "/remove <i>n</i> • /move <i>from to</i> • /clear\n"
        "/like: save the current song to <b>your</b> playlist\n"
        "/playlist: open your playlist (play it, remove songs, clear it)</blockquote>"
    ),
    "admin": (
        "👮 <b>Admin</b>\n\n"
        "<blockquote>/settings: who can play and who can control\n"
        "/auth <i>(reply or @user)</i>: let someone control the player\n"
        "/unauth • /authusers\n"
        "/reload: refresh the admin list</blockquote>"
    ),
    "owner": (
        "👑 <b>Owner</b>\n\n"
        "<blockquote>/stats • /usage: bot and API quota\n"
        "/broadcast <i>text</i> • /ban • /unban • /banned\n"
        "/sudo • /unsudo • /sudolist</blockquote>"
    ),
}

HOW = (
    "⚙️ <b>How to set me up</b>\n\n"
    "1. Add me to your group and make me an <b>admin</b> (Invite users, Manage voice chats).\n"
    "2. Start a voice chat in the group.\n"
    "3. Send /play and a song name. My assistant account joins automatically.\n\n"
    "Nothing to configure: just add, start the voice chat and play."
)

WELCOME = (
    "🎧 <b>Thanks for adding me!</b>\n\n"
    "1. Make me an <b>admin</b> (Invite users + Manage voice chats)\n"
    "2. Start a voice chat\n"
    "3. Send <code>/play song name</code>\n\n"
    "My assistant account joins by itself. See /help for everything I can do."
)

FINISH = {
    "queue_ended": "✅ <b>Queue finished.</b> I left the voice chat. Add more with /play.",
    "alone": "👋 Everyone left the voice chat, so I left too.",
    "call_closed": "🔇 The voice chat ended, so I cleared the queue.",
    "errors": "⚠️ Several songs in a row could not be played, so I stopped.",
}


def start_text(bot_name: str) -> str:
    return (
        f"🎧 <b>{esc(bot_name)}</b>\n\n"
        "I play music and videos in your group's voice chat: fast, with a queue, "
        "loop, seek, volume and personal playlists.\n\n"
        "Add me to a group, start a voice chat and send <code>/play song name</code>."
    )
