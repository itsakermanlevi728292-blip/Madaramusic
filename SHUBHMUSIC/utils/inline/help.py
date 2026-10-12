from . import DANGER, PLAIN, PRIMARY, SUCCESS, button, markup

HELP_SECTIONS = {
    "play": ("🎵 Play", SUCCESS),
    "ctrl": ("🎛 Controls", PRIMARY),
    "list": ("📜 Queue & playlists", PRIMARY),
    "admin": ("👮 Admin", PLAIN),
    "owner": ("👑 Owner", DANGER),
}


def help_main():
    keys = list(HELP_SECTIONS)
    rows = [[button(HELP_SECTIONS[k][0], cb=f"hp:{k}", style=HELP_SECTIONS[k][1]) for k in keys[i:i + 2]]
            for i in range(0, len(keys), 2)]
    rows.append([button("🏠 Home", cb="hp:home", style=PRIMARY), button("✖️ Close", cb="hp:close", style=DANGER)])
    return markup(rows)


def help_back():
    return markup([[button("⬅️ Back", cb="hp:main", style=PRIMARY), button("✖️ Close", cb="hp:close", style=DANGER)]])
