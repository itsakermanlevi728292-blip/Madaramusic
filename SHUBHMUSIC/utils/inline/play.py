from SHUBHMUSIC.utils.stream.queue import ChatQueue

from . import DANGER, PLAIN, PRIMARY, SUCCESS, button, markup

SEEK_STEP = 15
VOLUME_STEP = 10

LOOP_ICON = {"off": "🔁", "track": "🔂", "queue": "🔁"}
LOOP_TEXT = {"off": "Loop", "track": "Loop: song", "queue": "Loop: all"}


def player_markup(q: ChatQueue):
    """The buttons under the now-playing card. Colours show the state: loop green = on, resume green, stop red."""
    link = q.current.link if q.current and q.current.link else ""
    pause = button("▶️ Resume", cb="pl:pause", style=SUCCESS) if q.paused else button("⏸ Pause", cb="pl:pause", style=PRIMARY)
    loop_style = PLAIN if q.loop == "off" else SUCCESS
    return markup([
        [pause, button("⏭ Skip", cb="pl:skip", style=PRIMARY), button("⏹ Stop", cb="pl:stop", style=DANGER)],
        [button(f"{LOOP_ICON[q.loop]} {LOOP_TEXT[q.loop]}", cb="pl:loop", style=loop_style),
         button("🔀 Shuffle", cb="pl:shuffle"), button("❤️ Save", cb="pl:save", style=SUCCESS)],
        [button(f"⏪ {SEEK_STEP}s", cb="pl:back"), button(f"🔉 {max(1, q.volume - VOLUME_STEP)}", cb="pl:vdown"),
         button(f"🔊 {min(200, q.volume + VOLUME_STEP)}", cb="pl:vup"), button(f"{SEEK_STEP}s ⏩", cb="pl:fwd")],
        [button("📜 Queue", cb="pl:queue", style=PRIMARY), button("🔄", cb="pl:refresh"),
         button("📋 Link", copy=link) if link else None, button("✖️", cb="pl:close", style=DANGER)],
    ])
