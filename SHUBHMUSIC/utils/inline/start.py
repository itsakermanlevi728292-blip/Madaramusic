from . import DANGER, PRIMARY, SUCCESS, button, markup

ADMIN_RIGHTS = "invite_users+manage_video_chats+delete_messages+pin_messages"


def start_panel(bot_username: str, support_chat: str = "", support_channel: str = ""):
    rows = [
        [button("➕ Add me to your group", url=f"https://t.me/{bot_username}?startgroup=true&admin={ADMIN_RIGHTS}", style=SUCCESS)],
        [button("📖 Commands", cb="hp:main", style=PRIMARY), button("⚙️ How it works", cb="hp:how", style=PRIMARY)],
    ]
    links = []
    if support_chat:
        links.append(button("💬 Support", url=support_chat, style=DANGER))
    if support_channel:
        links.append(button("📣 Updates", url=support_channel, style=PRIMARY))
    rows.append(links)
    return markup(rows)
