import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from SHUBHMUSIC.platforms.Youtube import YouTubeAPI, Track  # noqa: E402
from config import Config  # noqa: E402
from SHUBHMUSIC.utils.database import Store  # noqa: E402


def make_config(**over) -> Config:
    env = dict(
        API_ID="1", API_HASH="hash", BOT_TOKEN="1:token", STRING_SESSION="sess",
        API_URL="https://api.test", API_KEY="myk_test", OWNER_ID="111",
    )
    env.update({k: str(v) for k, v in over.items()})
    return Config.from_env(env)


def tr(i=1, **kw) -> Track:
    base = dict(id=f"vid{i:08d}"[:11].ljust(11, "x"), title=f"Song {i}", duration=200, channel="Chan", thumbnail="")
    base.update(kw)
    return Track(**base)


class FakeAPI:
    """Stands in for YouTubeAPI inside player tests."""

    def __init__(self):
        self.plays: list[tuple[str, bool]] = []
        self.fail: dict[str, Exception] = {}
        self.limit_after: int | None = None

    async def play(self, video_id, *, video=False):
        from SHUBHMUSIC.platforms.Youtube import DailyLimitReached, Stream

        if video_id in self.fail:
            raise self.fail[video_id]
        if self.limit_after is not None and len(self.plays) >= self.limit_after:
            raise DailyLimitReached("limit", "daily_limit_reached", 429, retry_after=3600)
        self.plays.append((video_id, video))
        return Stream(track=Track(id=video_id, title="t"), url=f"https://api.test/v1/stream/{video_id}", counted=True)


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple] = []
        self.active: set[int] = set()
        self.fail_play: Exception | None = None
        self.listeners: int | None = 3

    async def play(self, chat_id, url, *, video=False, seek=0):
        if self.fail_play:
            raise self.fail_play
        self.calls.append(("play", chat_id, url, video, seek))
        self.active.add(chat_id)

    async def pause(self, chat_id):
        self.calls.append(("pause", chat_id))

    async def resume(self, chat_id):
        self.calls.append(("resume", chat_id))

    async def stop(self, chat_id):
        self.calls.append(("stop", chat_id))
        self.active.discard(chat_id)

    async def set_volume(self, chat_id, volume):
        self.calls.append(("volume", chat_id, volume))

    async def participants(self, chat_id):
        return self.listeners

    async def is_active(self, chat_id):
        return chat_id in self.active


class FakeNotifier:
    def __init__(self):
        self.events: list[tuple] = []

    async def now_playing(self, chat_id, queue):
        self.events.append(("now", chat_id, queue.current.title if queue.current else None))

    async def finished(self, chat_id, reason):
        self.events.append(("finished", chat_id, reason))

    async def failed(self, chat_id, text):
        self.events.append(("failed", chat_id, text))

    async def limit_reached(self, chat_id, retry_after):
        self.events.append(("limit", chat_id, retry_after))


@pytest.fixture
async def store():
    s = Store(":memory:")
    await s.open()
    yield s
    await s.close()


@pytest.fixture
async def rig(store):
    from SHUBHMUSIC.core.player import Player

    cfg = make_config()
    api, backend, notifier = FakeAPI(), FakeBackend(), FakeNotifier()
    player = Player(cfg, api, backend, store, notifier)
    player.clock = lambda: 1000.0  # frozen unless a test moves it
    return type("Rig", (), dict(cfg=cfg, api=api, backend=backend, notifier=notifier, player=player, store=store))
