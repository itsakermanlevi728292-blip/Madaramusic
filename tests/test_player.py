import asyncio

import pytest

from SHUBHMUSIC.platforms.Youtube import APIError, InvalidAPIKey, NotFound
from SHUBHMUSIC.utils.exceptions import NoVoiceChat, PlaybackError
from SHUBHMUSIC.core.player import ChatLimitReached, QueueFull
from .conftest import make_config, tr

C = -1001


async def add(rig, *tracks, **kw):
    return await rig.player.add(C, list(tracks), user_id=7, user_name="Rahul", **kw)


async def test_first_song_starts_and_later_ones_queue(rig):
    r = await add(rig, tr(1))
    assert r.started and r.position == 0
    assert rig.backend.calls[0][:3] == ("play", C, "https://api.test/v1/stream/" + tr(1).id)
    r2 = await add(rig, tr(2), tr(3))
    assert not r2.started and r2.position == 1 and r2.added == 2
    r3 = await add(rig, tr(4))
    assert r3.position == 3
    assert rig.notifier.events == [("now", C, "Song 1")]
    q = rig.player.queue(C)
    assert q.current.requested_name == "Rahul" and q.current.requested_by == 7
    assert [t.title for t in q.upcoming] == ["Song 2", "Song 3", "Song 4"]
    # queueing a song must NOT use up the API's daily limit: only the playing one was resolved
    assert [p[0] for p in rig.api.plays] == [tr(1).id]


async def test_stream_end_moves_on_and_finishes(rig):
    await add(rig, tr(1), tr(2))
    clock = {"t": 1000.0}
    rig.player.clock = lambda: clock["t"]
    clock["t"] = 1010
    await rig.player.on_stream_end(C)
    assert rig.player.queue(C).current.title == "Song 2"
    assert rig.notifier.events[-1] == ("now", C, "Song 2")
    clock["t"] = 1020
    await rig.player.on_stream_end(C)
    assert rig.notifier.events[-1] == ("finished", C, "queue_ended")
    assert rig.backend.calls[-1] == ("stop", C) and rig.player.queue(C).current is None


async def test_duplicate_stream_end_events_do_not_skip_songs(rig):
    await add(rig, tr(1), tr(2), tr(3))
    q = rig.player.queue(C)
    q.mark_started(0, now=500.0)
    clock = {"t": 500.2}  # an event 0.2s after the song started is stale / duplicate
    rig.player.clock = lambda: clock["t"]
    await rig.player.on_stream_end(C)
    assert q.current.title == "Song 1"
    clock["t"] = 530
    await asyncio.gather(rig.player.on_stream_end(C), rig.player.on_stream_end(C))
    assert q.current.title == "Song 2"  # two simultaneous real events advance only once


async def test_skip_stop_pause_resume(rig):
    await add(rig, tr(1), tr(2))
    gone, nxt = await rig.player.skip(C)
    assert gone.title == "Song 1" and nxt.title == "Song 2"
    assert await rig.player.pause(C) and not await rig.player.pause(C)
    assert rig.player.queue(C).paused
    assert await rig.player.resume(C) and not await rig.player.resume(C)
    gone, nxt = await rig.player.skip(C)
    assert nxt is None and rig.notifier.events[-1] == ("finished", C, "queue_ended")
    assert await rig.player.skip(C) is None  # nothing playing
    await add(rig, tr(5))
    assert await rig.player.stop(C) and not await rig.player.stop(C)
    assert rig.player.queue(C).current is None


async def test_loop_track_repeats_but_skip_still_moves_on(rig):
    await add(rig, tr(1), tr(2))
    assert await rig.player.cycle_loop(C) == "track"
    rig.player.queue(C).mark_started(0, now=0.0)
    await rig.player.on_stream_end(C)
    assert rig.player.queue(C).current.title == "Song 1"  # looped
    assert [p[0] for p in rig.api.plays].count(tr(1).id) == 2
    await rig.player.skip(C)
    assert rig.player.queue(C).current.title == "Song 2"


async def test_seek_replays_same_url_from_offset_and_keeps_pause_state(rig):
    await add(rig, tr(1, duration=200))
    assert await rig.player.seek(C, absolute=90) == 90
    assert rig.backend.calls[-1] == ("play", C, "https://api.test/v1/stream/" + tr(1).id, False, 90)
    assert len(rig.api.plays) == 1  # seeking does not cost another song
    assert await rig.player.seek(C, absolute=500) is None  # past the end
    await rig.player.pause(C)
    assert await rig.player.seek(C, absolute=10) == 10
    assert rig.backend.calls[-1] == ("pause", C) and rig.player.queue(C).paused


async def test_volume_clamped(rig):
    await add(rig, tr(1))
    assert await rig.player.set_volume(C, 500) == 200
    assert await rig.player.set_volume(C, -4) == 1
    assert await rig.player.set_volume(-999, 50) is None


async def test_bad_track_is_skipped_with_a_message(rig):
    rig.api.fail[tr(2).id] = NotFound("gone", "video_unavailable", 404)
    await add(rig, tr(1), tr(2), tr(3))
    await rig.player.skip(C)
    assert rig.player.queue(C).current.title == "Song 3"
    assert any(e[0] == "failed" and "Song 2" in e[2] for e in rig.notifier.events)


async def test_all_tracks_failing_stops_cleanly(rig):
    for i in (1, 2):
        rig.api.fail[tr(i).id] = APIError("x", "boom", 502)
    r = await add(rig, tr(1), tr(2))
    q = rig.player.queue(C)
    assert q.current is None and rig.notifier.events[-1] == ("finished", C, "queue_ended")
    assert sum(1 for e in rig.notifier.events if e[0] == "failed") == 2


async def test_daily_limit_stops_and_tells_the_chat(rig):
    rig.api.limit_after = 1
    await add(rig, tr(1), tr(2))
    await rig.player.skip(C)
    assert ("limit", C, 3600) in rig.notifier.events
    assert rig.player.queue(C).current is None and rig.player.queue(C).upcoming == type(rig.player.queue(C).upcoming)()


async def test_invalid_key_is_reported(rig):
    rig.api.fail[tr(1).id] = InvalidAPIKey("bad key", "invalid_api_key", 401)
    await add(rig, tr(1))
    assert rig.notifier.events[-1][0] == "failed" and "bad key" in rig.notifier.events[-1][2]


async def test_no_voice_chat_does_not_burn_through_the_queue(rig):
    rig.backend.fail_play = NoVoiceChat("start a voice chat")
    await add(rig, tr(1), tr(2), tr(3))
    assert rig.notifier.events[-1] == ("failed", C, "start a voice chat")
    assert rig.player.queue(C).current is None and not rig.player.queue(C).upcoming


async def test_library_errors_become_friendly_messages(rig):
    rig.backend.fail_play = RuntimeError("ntgcalls exploded: secret path /x/y")
    await add(rig, tr(1))
    texts = [e[2] for e in rig.notifier.events if e[0] == "failed"]
    assert texts and all("ntgcalls" not in t and "secret" not in t for t in texts)


async def test_queue_cap_and_truncation(store):
    from SHUBHMUSIC.core.player import Player
    from .conftest import FakeAPI, FakeBackend, FakeNotifier

    cfg = make_config(MAX_QUEUE=3)
    p = Player(cfg, FakeAPI(), FakeBackend(), store, FakeNotifier())
    r = await p.add(C, [tr(i) for i in range(1, 6)], user_id=1, user_name="a")
    assert r.added == 3 and r.dropped == 2
    with pytest.raises(QueueFull):
        await p.add(C, [tr(9)], user_id=1, user_name="a")


async def test_duration_limit(store):
    from SHUBHMUSIC.core.player import Player
    from .conftest import FakeAPI, FakeBackend, FakeNotifier

    cfg = make_config(DURATION_LIMIT_MIN=5)
    n = FakeNotifier()
    p = Player(cfg, FakeAPI(), FakeBackend(), store, n)
    await p.add(C, [tr(1, duration=301), tr(2, duration=60)], user_id=1, user_name="a")
    assert p.queue(C).current.title == "Song 2"
    assert any(e[0] == "failed" and "5-minute" in e[2] for e in n.events)


async def test_force_play_jumps_the_queue(rig):
    await add(rig, tr(1), tr(2))
    r = await add(rig, tr(9), force=True)
    assert r.started and rig.player.queue(C).current.title == "Song 9"
    assert [t.title for t in rig.player.queue(C).upcoming] == ["Song 2"]


async def test_per_chat_daily_cap(store):
    from SHUBHMUSIC.core.player import Player
    from .conftest import FakeAPI, FakeBackend, FakeNotifier

    p = Player(make_config(PLAYS_PER_CHAT_PER_DAY=2), FakeAPI(), FakeBackend(), store, FakeNotifier())
    await p.add(C, [tr(1), tr(2)], user_id=1, user_name="a")
    await p.skip(C)
    assert await store.chat_plays_today(C) == 2
    with pytest.raises(ChatLimitReached):
        await p.add(C, [tr(3)], user_id=1, user_name="a")
    await p.add(-77, [tr(3)], user_id=1, user_name="a")  # other chats are unaffected


async def test_video_flag_reaches_the_api_and_backend(rig):
    await add(rig, tr(1), video=True)
    assert rig.api.plays[-1] == (tr(1).id, True) and rig.backend.calls[0][3] is True


async def test_call_closed_externally_clears_everything(rig):
    await add(rig, tr(1), tr(2))
    await rig.player.on_call_closed(C)
    q = rig.player.queue(C)
    assert q.current is None and not q.upcoming and rig.notifier.events[-1] == ("finished", C, "call_closed")
    await rig.player.on_call_closed(-5)  # unknown chat: no crash


async def test_housekeeping_leaves_when_alone_and_cleans_dead_calls(rig):
    await add(rig, tr(1))
    clock = {"t": 1000.0}
    rig.player.clock = lambda: clock["t"]
    rig.backend.listeners = 1
    await rig.player.housekeeping_once()
    assert rig.player.queue(C).current is not None  # first sighting only starts the timer
    clock["t"] = 1061
    await rig.player.housekeeping_once()
    assert rig.notifier.events[-1] == ("finished", C, "alone")
    # a call that vanished behind our back
    rig.backend.listeners = 4
    await add(rig, tr(2))
    rig.backend.active.clear()
    clock["t"] = 2000
    await rig.player.housekeeping_once()
    assert rig.notifier.events[-1] == ("finished", C, "call_closed")


async def test_idle_queues_are_forgotten(rig):
    rig.player.queue(-42)
    clock = {"t": 1000.0}
    rig.player.clock = lambda: clock["t"]
    rig.player.queue(-43)
    clock["t"] = 1000 + rig.cfg.auto_leave_seconds + 1
    await rig.player.housekeeping_once()
    assert -43 not in rig.player.queues
