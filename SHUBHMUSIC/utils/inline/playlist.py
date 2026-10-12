from . import DANGER, SUCCESS, button, markup


def playlist_markup(count: int):
    rows = []
    if count:
        rows.append([button("▶️ Play all", cb="pm:play", style=SUCCESS), button("🗑 Clear", cb="pm:clear", style=DANGER)])
    rows.append([button("✖️ Close", cb="pm:close", style=DANGER)])
    return markup(rows)
