"""Playback brain: queue + API + call backend. Nothing here talks to Telegram directly,
so the whole thing is testable with fakes."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from SHUBHMUSIC.platforms.Youtube import APIError, DailyLimitReached, InvalidAPIKey, YouTubeAPI, Track
from config import Config
from SHUBHMUSIC.utils.exceptions import BotError, NoVoiceChat, PlaybackError
from SHUBHMUSIC.utils.stream.queue import ChatQueue
from SHUBHMUSIC.utils.database import Store

log = logging.getLogger("SHUBHMUSIC.core.player")

MAX_START_ATTEMPTS = 5  # bad tracks in a row we are willing to skip before giving up


class Backend(Protocol):
    async def play(self, chat_id: int, url: str, *, video: bool = False, seek: int = 0) -> None: ...
    async def pause(self, chat_id: int) -> None: ...
    async def resume(self, chat_id: int) -> None: ...
    async def stop(self, chat_id: int) -> None: ...
    async def set_volume(self, chat_id: int, volume: int) -> None: ...
    async def participants(self, chat_id: int) -> int | None: ...
    async def is_active(self, chat_id: int) -> bool: ...


class Notifier(Protocol):
    async def now_playing(self, chat_id: int, queue: ChatQueue) -> None: ...
    async def finished(self, chat_id: int, reason: str) -> None: ...
    async def failed(self, chat_id: int, text: str) -> None: ...
    async def limit_reached(self, chat_id: int, retry_after: int) -> None: ...


@dataclass
class AddResult:
    started: bool
    position: int  # 0 = playing now, otherwise place in the queue
    added: int
    dropped: int = 0  # tracks that did not fit in the queue
    first: Track | None = None


class QueueFull(BotError):
    pass


class ChatLimitReached(BotError):
    pass


class Player:
    def __init__(self, cfg: Config, api: YouTubeAPI, backend: Backend, store: Store, notifier: Notifier):
        self.cfg, self.api, self.backend, self.store, self.notifier = cfg, api, backend, store, notifier
        self.queues: dict[int, ChatQueue] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._urls: dict[int, str] = {}
        self._alone_since: dict[int, float] = {}
        self._task: asyncio.Task | None = None
        self.clock = time.monotonic

    # ── access ────────────────────────────────────────────────────────────
    def queue(self, chat_id: int) -> ChatQueue:
        q = self.queues.get(chat_id)
        if q is None:
            q = self.queues[chat_id] = ChatQueue(chat_id)
            q.idle_since = self.clock()
        return q

    def lock(self, chat_id: int) -> asyncio.Lock:
        lk = self._locks.get(chat_id)
        if lk is None:
            lk = self._locks[chat_id] = asyncio.Lock()
        return lk

    def active_chats(self) -> list[int]:
        return [c for c, q in self.queues.items() if q.current is not None]

    # ── adding songs ──────────────────────────────────────────────────────
    async def add(self, chat_id: int, tracks: list[Track], *, user_id: int, user_name: str,
                  video: bool = False, force: bool = False) -> AddResult:
        if not tracks:
            raise BotError("Nothing to add.")
        cap = self.cfg.plays_per_chat_per_day
        if cap and await self.store.chat_plays_today(chat_id) >= cap:
            raise ChatLimitReached(
                f"This group used its {cap} songs for today. The limit resets at midnight."
            )
        async with self.lock(chat_id):
            q = self.queue(chat_id)
            room = self.cfg.max_queue - len(q)
            if room <= 0:
                raise QueueFull(f"The queue is full ({self.cfg.max_queue} songs). Wait for some to finish.")
            fitting = tracks[:room]
            ready = [dataclasses.replace(t, requested_by=user_id, requested_name=user_name, video=video) for t in fitting]
            starting = q.current is None
            if force and not starting:
                for t in reversed(ready):
                    q.add(t, front=True)
                await self._advance_and_start(chat_id, manual=True)
                position = 0
            elif starting:
                for t in ready:
                    q.add(t)
                await self._advance_and_start(chat_id, manual=True)
                position = 0
            else:
                for t in ready:
                    q.add(t)
                position = len(q.upcoming) - len(ready) + 1
            return AddResult(started=starting or force, position=position, added=len(ready),
                             dropped=len(tracks) - len(fitting), first=ready[0])

    # ── starting and advancing (call with the chat lock held) ─────────────
    async def _advance_and_start(self, chat_id: int, *, manual: bool) -> None:
        q = self.queue(chat_id)
        for _ in range(MAX_START_ATTEMPTS):
            track = q.advance(manual=manual)
            if track is None:
                await self._finish(chat_id, "queue_ended")
                return
            try:
                await self._start(chat_id, q, track)
                await self._announce(chat_id, q)
                return
            except DailyLimitReached as e:
                await self._finish(chat_id, "limit", notify=False)
                try:
                    await self.notifier.limit_reached(chat_id, e.retry_after)
                except Exception:
                    log.exception("limit notification failed in %s", chat_id)
                return
            except InvalidAPIKey as e:
                await self._finish(chat_id, "bad_key", notify=False)
                await self._safe_failed(chat_id, e.message)
                return
            except NoVoiceChat as e:
                await self._finish(chat_id, "no_vc", notify=False)
                await self._safe_failed(chat_id, str(e))
                return
            except (APIError, PlaybackError, BotError) as e:
                log.warning("skipping %s in %s: %s", track.id, chat_id, e)
                await self._safe_failed(chat_id, f"Could not play “{track.title}”: {getattr(e, 'message', None) or e}")
                manual = True  # a broken song must not be repeated by 'loop this track'
        await self._finish(chat_id, "errors")

    async def _start(self, chat_id: int, q: ChatQueue, track: Track, seek: int = 0) -> None:
        limit = self.cfg.duration_limit_seconds
        if limit and track.duration and track.duration > limit:
            raise BotError(f"longer than the {self.cfg.duration_limit_min}-minute limit")
        stream = await self.api.play(track.id, video=track.video)
        try:
            await self.backend.play(chat_id, stream.url, video=track.video, seek=seek)
        except BotError:
            raise
        except Exception as e:  # a library error: show something friendly, keep the details in the log
            log.exception("backend.play failed in %s", chat_id)
            raise PlaybackError("The voice chat could not start this song.") from e
        self._urls[chat_id] = stream.url
        q.mark_started(seek, now=self.clock())
        if stream.counted and not seek:
            try:
                await self.store.add_chat_play(chat_id)
            except Exception:
                log.exception("could not record the play")

    async def _announce(self, chat_id: int, q: ChatQueue) -> None:
        try:
            await self.notifier.now_playing(chat_id, q)
        except Exception:
            log.exception("now_playing notification failed in %s", chat_id)

    async def _safe_failed(self, chat_id: int, text: str) -> None:
        try:
            await self.notifier.failed(chat_id, text)
        except Exception:
            log.exception("failure notification failed in %s", chat_id)

    async def _finish(self, chat_id: int, reason: str, *, notify: bool = True) -> None:
        q = self.queue(chat_id)
        q.reset()
        q.idle_since = self.clock()
        self._urls.pop(chat_id, None)
        self._alone_since.pop(chat_id, None)
        try:
            await self.backend.stop(chat_id)
        except Exception:
            log.debug("leave call failed in %s", chat_id, exc_info=True)
        if notify:
            try:
                await self.notifier.finished(chat_id, reason)
            except Exception:
                log.exception("finished notification failed in %s", chat_id)

    # ── events from the call layer ────────────────────────────────────────
    async def on_stream_end(self, chat_id: int) -> None:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None:
                return
            if self.clock() - q.last_advance < 1.5:  # duplicate / stale event right after a switch
                return
            await self._advance_and_start(chat_id, manual=False)

    async def on_call_closed(self, chat_id: int) -> None:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None and not q.upcoming:
                return
            await self._finish(chat_id, "call_closed", notify=True)

    # ── controls ──────────────────────────────────────────────────────────
    async def skip(self, chat_id: int) -> tuple[Track, Track | None] | None:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None:
                return None
            gone = q.current
            await self._advance_and_start(chat_id, manual=True)
            return gone, q.current

    async def stop(self, chat_id: int) -> bool:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or (q.current is None and not q.upcoming):
                return False
            await self._finish(chat_id, "stopped", notify=False)
            return True

    async def pause(self, chat_id: int) -> bool:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None or q.paused:
                return False
            await self.backend.pause(chat_id)
            q.mark_paused(now=self.clock())
            return True

    async def resume(self, chat_id: int) -> bool:
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None or not q.paused:
                return False
            await self.backend.resume(chat_id)
            q.mark_resumed(now=self.clock())
            return True

    async def seek(self, chat_id: int, *, delta: int | None = None, absolute: int | None = None) -> int | None:
        """Returns the new position in seconds, or None if that is not possible."""
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None:
                return None
            target = q.seek_target(delta=delta, absolute=absolute)
            if target is None:
                return None
            was_paused = q.paused
            url = self._urls.get(chat_id)
            if not url:
                url = (await self.api.play(q.current.id, video=q.current.video)).url
            try:
                await self.backend.play(chat_id, url, video=q.current.video, seek=target)
            except Exception as e:
                log.exception("seek failed in %s", chat_id)
                raise PlaybackError("Could not jump to that position.") from e
            self._urls[chat_id] = url
            q.mark_started(target, now=self.clock())
            if was_paused:
                await self.backend.pause(chat_id)
                q.mark_paused(now=self.clock())
            return target

    async def set_volume(self, chat_id: int, volume: int) -> int | None:
        volume = max(1, min(200, int(volume)))
        async with self.lock(chat_id):
            q = self.queues.get(chat_id)
            if q is None or q.current is None:
                return None
            await self.backend.set_volume(chat_id, volume)
            q.volume = volume
            return volume

    async def cycle_loop(self, chat_id: int) -> str | None:
        q = self.queues.get(chat_id)
        if q is None or q.current is None:
            return None
        return q.cycle_loop()

    # ── housekeeping ──────────────────────────────────────────────────────
    async def housekeeping_once(self) -> None:
        now = self.clock()
        for chat_id in list(self.queues):
            q = self.queues[chat_id]
            if q.current is None:
                if q.idle_since and now - q.idle_since > self.cfg.auto_leave_seconds:
                    self.queues.pop(chat_id, None)
                    self._locks.pop(chat_id, None)
                continue
            try:
                active = await self.backend.is_active(chat_id)
            except Exception:
                active = True
            if not active and now - q.last_advance > 20:
                await self.on_call_closed(chat_id)
                continue
            try:
                n = await self.backend.participants(chat_id)
            except Exception:
                n = None
            if n is not None and n <= 1:
                since = self._alone_since.setdefault(chat_id, now)
                if now - since >= 60:
                    async with self.lock(chat_id):
                        await self._finish(chat_id, "alone")
            else:
                self._alone_since.pop(chat_id, None)

    def start_housekeeping(self, every: float = 20.0) -> None:
        async def loop():
            while True:
                await asyncio.sleep(every)
                try:
                    await self.housekeeping_once()
                except Exception:
                    log.exception("housekeeping failed")

        if self._task is None:
            self._task = asyncio.create_task(loop())

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
