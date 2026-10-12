from . import DANGER, PRIMARY, button, markup


def search_markup(token: str, tracks):
    rows = [[button(f"{i}. {t.title[:44]}", cb=f"sr:{token}:{i - 1}", style=PRIMARY)] for i, t in enumerate(tracks, 1)]
    rows.append([button("✖️ Close", cb=f"sr:{token}:x", style=DANGER)])
    return markup(rows)
