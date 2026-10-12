"""Per-chat queue and playback timing. Pure Python, no Telegram, easy to test."""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field

from SHUBHMUSIC.platforms.Youtube import Track

LOOP_OFF, LOOP_TRACK, LOOP_QUEUE = "off", "track", "queue"
LOOP_CYCLE = (LOOP_OFF, LOOP_TRACK, LOOP_QUEUE)


@dataclass
class ChatQueue:
    chat_id: int
    current: Track | None = None
    upcoming: deque = field(default_factory=deque)
    loop: str = LOOP_OFF
    volume: int = 100
    # playback clock
    generation: int = 0  # bumps every time a new stream starts, used to ignore stale events
    _started_at: float = 0.0  # monotonic time when the current offset began
    _offset: float = 0.0  # seconds into the track at _started_at
    _paused_at: float | None = None
    last_message_id: int | None = None  # the "now playing" card, so we can tidy it up
    idle_since: float | None = None
    last_advance: float = 0.0

    # ── queue editing ─────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self.upcoming) + (1 if self.current else 0)

    def add(self, track: Track, *, front: bool = False) -> int:
        """Returns the 1-based position of the track (0 means it plays right away)."""
        if front:
            self.upcoming.appendleft(track)
            return 1 if self.current else 0
        self.upcoming.append(track)
        return len(self.upcoming) if self.current else 0

    def remove(self, position: int) -> Track | None:
        """Remove upcoming track number `position` (1 = next up). The playing song cannot be removed."""
        if position < 1 or position > len(self.upcoming):
            return None
        items = list(self.upcoming)
        gone = items.pop(position - 1)
        self.upcoming = deque(items)
        return gone

    def clear(self) -> int:
        n = len(self.upcoming)
        self.upcoming.clear()
        return n

    def shuffle(self) -> bool:
        if len(self.upcoming) < 2:
            return False
        items = list(self.upcoming)
        random.shuffle(items)
        self.upcoming = deque(items)
        return True

    def move(self, src: int, dst: int) -> bool:
        n = len(self.upcoming)
        if not (1 <= src <= n and 1 <= dst <= n):
            return False
        items = list(self.upcoming)
        items.insert(dst - 1, items.pop(src - 1))
        self.upcoming = deque(items)
        return True

    def cycle_loop(self) -> str:
        self.loop = LOOP_CYCLE[(LOOP_CYCLE.index(self.loop) + 1) % len(LOOP_CYCLE)]
        return self.loop

    # ── advancing ─────────────────────────────────────────────────────────
    def advance(self, *, manual: bool = False) -> Track | None:
        """Pick the next track. A manual skip ignores 'loop this track'."""
        prev = self.current
        if prev is not None and not manual and self.loop == LOOP_TRACK:
            return prev
        if prev is not None and self.loop == LOOP_QUEUE:
            self.upcoming.append(prev)
        self.current = self.upcoming.popleft() if self.upcoming else None
        return self.current

    def reset(self) -> None:
        self.current = None
        self.upcoming.clear()
        self.loop = LOOP_OFF
        self._offset, self._started_at, self._paused_at = 0.0, 0.0, None

    # ── playback clock ────────────────────────────────────────────────────
    def mark_started(self, offset: float = 0.0, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.generation += 1
        self._offset, self._started_at, self._paused_at = float(offset), now, None
        self.idle_since = None
        self.last_advance = now

    def mark_paused(self, now: float | None = None) -> None:
        if self._paused_at is None:
            self._paused_at = time.monotonic() if now is None else now

    def mark_resumed(self, now: float | None = None) -> None:
        if self._paused_at is not None:
            now = time.monotonic() if now is None else now
            self._started_at += now - self._paused_at
            self._paused_at = None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def position(self, now: float | None = None) -> int:
        if not self.current:
            return 0
        now = time.monotonic() if now is None else now
        ref = self._paused_at if self._paused_at is not None else now
        pos = self._offset + max(0.0, ref - self._started_at)
        dur = self.current.duration
        return int(min(pos, dur) if dur else pos)

    def seek_target(self, *, delta: int | None = None, absolute: int | None = None) -> int | None:
        """Where a seek would land, or None if the song is too short / the target is out of range."""
        if not self.current or not self.current.duration:
            return None
        target = absolute if absolute is not None else self.position() + (delta or 0)
        target = max(0, target)
        if target >= self.current.duration - 2:
            return None
        return target
