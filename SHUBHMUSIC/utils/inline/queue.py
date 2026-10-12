from . import DANGER, PRIMARY, button, markup


def queue_markup(page: int, pages: int):
    row = []
    if page > 0:
        row.append(button("◀️ Prev", cb=f"qu:{page - 1}", style=PRIMARY))
    row.append(button(f"{page + 1}/{pages}", cb="qu:noop"))
    if page < pages - 1:
        row.append(button("Next ▶️", cb=f"qu:{page + 1}", style=PRIMARY))
    return markup([row, [button("⬅️ Back to player", cb="pl:refresh", style=PRIMARY), button("✖️ Close", cb="pl:close", style=DANGER)]])
