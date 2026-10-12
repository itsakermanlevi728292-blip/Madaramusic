"""Message text. HTML parse mode everywhere, and user-controlled text is always escaped."""

from __future__ import annotations

import html

from ..api import Track
from ..queue import LOOP_OFF, LOOP_QUEUE, LOOP_TRACK, ChatQueue

LOOP_LABEL = {LOOP_OFF: "Off", LOOP_TRACK: "This song", LOOP_QUEUE: "Whole queue"}


def esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


def fmt_time(seconds: int | float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_time(text: str) -> int | None:
    """'90', '1:30', '1:02:03' -> seconds. Anything else -> None."""
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3 or not all(p.isdigit() for p in parts):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def progress_bar(position: int, duration: int, width: int = 14) -> str:
    if duration <= 0:
        return "━" * width
    filled = min(width - 1, int(width * min(position, duration) / duration))
    return "━" * filled + "●" + "─" * (width - 1 - filled)


def short(text: str, limit: int = 48) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def now_playing(q: ChatQueue, bot_name: str) -> str:
    t = q.current
    if t is None:
        return "Nothing is playing right now."
    pos = q.position()
    state = "⏸ <b>Paused</b>" if q.paused else "▶️ <b>Now playing</b>"
    kind = "🎬 Video" if t.video else "🎧 Audio"
    lines = [
        state,
        "",
        f"<b>{esc(short(t.title, 70))}</b>",
        f"👤 {esc(t.channel) or 'Unknown artist'}",
        "",
        f"<code>{fmt_time(pos)}  {progress_bar(pos, t.duration)}  {fmt_time(t.duration) if t.duration else 'live'}</code>",
        "",
        f"{kind}  •  🔁 {LOOP_LABEL[q.loop]}  •  🔊 {q.volume}%",
    ]
    if t.requested_name:
        lines.append(f"🙋 {esc(t.requested_name)}")
    if q.upcoming:
        lines.append(f"📜 {len(q.upcoming)} more in the queue")
    return "\n".join(lines)


def added(track: Track, position: int, count: int, dropped: int) -> str:
    if count > 1:
        text = f"✅ <b>{count} songs</b> added to the queue (starting at #{position})."
    else:
        text = f"✅ <b>{esc(short(track.title, 60))}</b>\n⏱ {fmt_time(track.duration)} • queued at <b>#{position}</b>"
    if dropped:
        text += f"\n⚠️ {dropped} did not fit: the queue is full."
    return text


def queue_page(q: ChatQueue, page: int = 0, per_page: int = 10) -> tuple[str, int]:
    """Returns (text, number_of_pages)."""
    pages = max(1, -(-len(q.upcoming) // per_page))
    page = max(0, min(page, pages - 1))
    lines = []
    if q.current:
        lines.append(f"▶️ <b>{esc(short(q.current.title, 55))}</b>  <code>{fmt_time(q.current.duration)}</code>")
    if not q.upcoming:
        lines.append("\nThe queue is empty. Add songs with /play.")
        return "\n".join(lines) or "The queue is empty.", 1
    lines.append("")
    start = page * per_page
    for i, t in enumerate(list(q.upcoming)[start:start + per_page], start=start + 1):
        lines.append(f"<b>{i}.</b> {esc(short(t.title, 50))}  <code>{fmt_time(t.duration)}</code>")
    total = sum(t.duration for t in q.upcoming)
    lines.append(f"\n📜 {len(q.upcoming)} songs • ⏱ {fmt_time(total)} • page {page + 1}/{pages}")
    return "\n".join(lines), pages


def limit_message(retry_after: int) -> str:
    when = ""
    if retry_after:
        h, m = divmod(max(1, retry_after) // 60, 60)
        when = f" It resets in about {h}h {m}m." if h else f" It resets in about {m} minutes."
    return (
        "⚠️ <b>Daily song limit reached.</b>\n"
        "The music server has no songs left for today." + when + "\n"
        "Playback stopped. The bot owner can upgrade the plan for more."
    )
