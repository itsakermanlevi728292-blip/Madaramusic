import httpx
import pytest

from bot.api import DailyLimitReached, InvalidAPIKey, MusicAPI, NotFound, Unavailable
from bot.config import Config, ConfigError
from bot.queue import ChatQueue, LOOP_QUEUE, LOOP_TRACK
from .conftest import make_config, tr


# ── config ────────────────────────────────────────────────────────────────
def test_config_requires_the_essentials():
    with pytest.raises(ConfigError) as e:
        Config.from_env({})
    assert "API_URL" in str(e.value) and "STRING_SESSION" in str(e.value)


def test_config_parses_and_validates():
    cfg = make_config(API_URL="https://api.test/", OWNER_ID="1, 2 3", STRING_SESSION2="b")
    assert cfg.api_url == "https://api.test" and cfg.owner_ids == {1, 2, 3}
    assert cfg.session_strings == ("sess", "b")
    with pytest.raises(ConfigError):
        make_config(API_URL="ftp://nope")
    with pytest.raises(ConfigError):
        make_config(OWNER_ID="abc")
    with pytest.raises(ConfigError):
        make_config(MAX_QUEUE="many")


# ── queue ─────────────────────────────────────────────────────────────────
def test_queue_basic_flow():
    q = ChatQueue(1)
    assert q.add(tr(1)) == 0  # nothing playing yet
    assert q.advance().title == "Song 1"
    assert q.add(tr(2)) == 1 and q.add(tr(3)) == 2
    assert len(q) == 3
    assert q.advance().title == "Song 2"
    assert q.advance().title == "Song 3"
    assert q.advance() is None and q.current is None


def test_queue_loop_modes():
    q = ChatQueue(1)
    q.add(tr(1)); q.add(tr(2))
    q.advance()
    q.loop = LOOP_TRACK
    assert q.advance().title == "Song 1"  # natural end repeats
    assert q.advance(manual=True).title == "Song 2"  # skip ignores loop-track
    q.loop = LOOP_QUEUE
    assert q.advance().title == "Song 2"  # a one-song queue just repeats
    q.add(tr(3))
    assert q.advance().title == "Song 3"
    assert q.advance().title == "Song 2"  # and a longer queue wraps around
    assert q.cycle_loop() == "off"


def test_queue_remove_move_shuffle_clear():
    q = ChatQueue(1)
    for i in range(1, 6):
        q.add(tr(i))
    q.advance()
    assert [t.title for t in q.upcoming] == ["Song 2", "Song 3", "Song 4", "Song 5"]
    assert q.remove(2).title == "Song 3" and q.remove(9) is None and q.remove(0) is None
    assert q.move(3, 1) and [t.title for t in q.upcoming][0] == "Song 5"
    assert not q.move(1, 9)
    assert q.shuffle() and len(q.upcoming) == 3
    assert q.clear() == 3 and not q.shuffle()


def test_queue_clock_pause_seek():
    q = ChatQueue(1)
    q.add(tr(1, duration=100)); q.advance()
    q.mark_started(now=1000.0)
    assert q.position(now=1030.0) == 30
    q.mark_paused(now=1030.0)
    assert q.position(now=1090.0) == 30  # frozen while paused
    q.mark_resumed(now=1090.0)
    assert q.position(now=1100.0) == 40
    assert q.seek_target(delta=-100) == 0 and q.seek_target(absolute=99) is None
    assert q.seek_target(absolute=60) == 60
    g = q.generation
    q.mark_started(60, now=2000.0)
    assert q.generation == g + 1 and q.position(now=2010.0) == 70
    assert q.position(now=9999.0) == 100  # never past the end


# ── API client ────────────────────────────────────────────────────────────
def api_with(handler) -> MusicAPI:
    return MusicAPI("https://api.test", "myk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_api_search_track_and_play_shapes():
    seen = {}

    def handler(req: httpx.Request):
        seen[req.url.path] = (dict(req.url.params), req.headers.get("x-api-key"))
        if req.url.path == "/v1/search":
            return httpx.Response(200, json={"results": [{"id": "aaaaaaaaaaa", "title": "A", "duration": 90, "channel": "C"}]})
        if req.url.path == "/v1/track":
            return httpx.Response(200, json={"id": "aaaaaaaaaaa", "title": "A", "duration": 90})
        if req.url.path == "/v1/play":
            return httpx.Response(200, json={"id": "aaaaaaaaaaa", "title": "A", "duration": 90, "stream_url": "https://api.test/v1/stream/tok",
                                             "counted": True, "usage": {"plan": "free", "daily_limit": 1000, "used_today": 5, "remaining_today": 995}})
        if req.url.path == "/v1/me":
            return httpx.Response(200, json={"key": {"plan": "free", "plan_expires_at": None}, "usage": {"daily_limit": 1000, "used_today": 5, "remaining_today": 995}})
        return httpx.Response(404, json={})

    api = api_with(handler)
    res = await api.search("hello", 3)
    assert res[0].title == "A" and res[0].thumbnail.endswith("aaaaaaaaaaa/hqdefault.jpg")
    assert seen["/v1/search"] == ({"q": "hello", "limit": "3"}, "myk_test")
    assert (await api.track("hello")).id == "aaaaaaaaaaa"
    s = await api.play("aaaaaaaaaaa", video=True)
    assert s.url.endswith("/tok") and s.remaining_today == 995
    assert seen["/v1/play"][0] == {"id": "aaaaaaaaaaa", "type": "video"}
    u = await api.usage()
    assert u.daily_limit == 1000 and u.remaining_today == 995


async def test_api_error_mapping():
    def make(status, body, headers=None):
        return api_with(lambda r: httpx.Response(status, json=body, headers=headers or {}))

    with pytest.raises(DailyLimitReached) as e:
        await make(429, {"error": "daily_limit_reached", "message": "x"}, {"Retry-After": "3600"}).play("a" * 11)
    assert e.value.retry_after == 3600
    with pytest.raises(InvalidAPIKey):
        await make(401, {"error": "invalid_api_key", "message": "bad"}).search("x")
    with pytest.raises(NotFound):
        await make(404, {"error": "not_found", "message": "none"}).track("x")
    with pytest.raises(Unavailable):
        await make(502, {"error": "extraction_failed", "message": "yt down"}).play("a" * 11)
    with pytest.raises(Unavailable):
        await make(429, {"error": "rate_limited", "message": "slow"}).search("x")


async def test_api_retries_once_then_reports_unreachable():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(Unavailable) as e:
        await api_with(handler).search("x")
    assert calls["n"] == 2 and e.value.code == "unreachable"

    flaky = {"n": 0}

    def handler2(req):
        flaky["n"] += 1
        if flaky["n"] == 1:
            return httpx.Response(502, json={"error": "x", "message": "m"})
        return httpx.Response(200, json={"results": []})

    assert await api_with(handler2).search("x") == []


# ── store ─────────────────────────────────────────────────────────────────
async def test_store_settings_auth_bans_sudo(store):
    assert (await store.settings(5)) == {"play_mode": "everyone", "control_mode": "admins", "clean_commands": False}
    await store.set_setting(5, "play_mode", "admins")
    await store.set_setting(5, "clean_commands", True)
    s = await store.settings(5)
    assert s["play_mode"] == "admins" and s["clean_commands"] is True
    with pytest.raises(ValueError):
        await store.set_setting(5, "play_mode", "nobody")
    with pytest.raises(ValueError):
        await store.set_setting(5, "id; DROP TABLE chats", "x")
    assert await store.add_auth(5, 9) and not await store.add_auth(5, 9)
    assert await store.is_auth(5, 9) and not await store.is_auth(6, 9)
    assert await store.auth_list(5) == [9] and await store.remove_auth(5, 9) and not await store.remove_auth(5, 9)
    assert await store.ban_user(1) and await store.is_user_banned(1) and await store.ban_user(1, False)
    assert not await store.is_user_banned(1)
    assert await store.ban_chat(-100) and await store.is_chat_banned(-100)
    assert await store.set_sudo(7) and await store.is_sudo(7) and await store.sudo_list() == [7]
    assert await store.touch_user(3) is True and await store.touch_user(3) is False
    await store.touch_chat(-1); await store.touch_chat(-1)
    assert await store.chat_ids() == [-1, 5] or await store.chat_ids() == [-1]
    await store.forget_chat(5)
    assert (await store.counts())["users"] == 1


async def test_store_playlists(store):
    assert await store.playlist_add(1, tr(1)) == "added"
    assert await store.playlist_add(1, tr(1)) == "exists"
    assert await store.playlist_add(1, tr(2)) == "added"
    assert [t.title for t in await store.playlist_list(1)] == ["Song 1", "Song 2"]
    assert await store.playlist_list(2) == []
    assert not await store.playlist_remove(1, 5) and await store.playlist_remove(1, 1)
    assert [t.title for t in await store.playlist_list(1)] == ["Song 2"]
    assert await store.playlist_clear(1) == 1


async def test_store_playlist_limit(store):
    from bot.store import PLAYLIST_MAX

    for i in range(PLAYLIST_MAX):
        assert await store.playlist_add(1, tr(i, id=f"id{i:09d}")) == "added"
    assert await store.playlist_add(1, tr(999, id="zzzzzzzzzzz")) == "full"


async def test_store_chat_usage_counter(store):
    assert await store.chat_plays_today(-5) == 0
    assert await store.add_chat_play(-5) == 1 and await store.add_chat_play(-5) == 2
    assert await store.chat_plays_today(-5) == 2 and await store.chat_plays_today(-6) == 0
