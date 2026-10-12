"""Handler tests with fake Telegram objects: permissions, play flow, controls, buttons, owner tools."""

import asyncio
import types

import pytest
from pyrogram import enums

from SHUBHMUSIC.platforms.Youtube import DailyLimitReached, NotFound
from SHUBHMUSIC.core.context import Ctx, classify
from SHUBHMUSIC.utils.exceptions import AssistantError
from SHUBHMUSIC.plugins import register_all
from SHUBHMUSIC.core.player import Player

from .conftest import FakeAPI, FakeBackend, FakeNotifier, make_config, tr

CHAT = -1001
OWNER, ADMIN, MEMBER, OTHER = 111, 222, 333, 444


class FakeMsg:
    def __init__(self, text="", chat_id=CHAT, uid=MEMBER, reply=None, sender_chat=None, ctype=enums.ChatType.SUPERGROUP, photo=False):
        self.text, self.caption = text, None
        self.id = 1
        self.chat = types.SimpleNamespace(id=chat_id, type=ctype)
        self.from_user = None if uid is None else types.SimpleNamespace(
            id=uid, first_name=f"U{uid}", last_name=None, username=None, mention=f"@u{uid}")
        self.reply_to_message = reply
        self.sender_chat = sender_chat
        self.photo = photo
        self.replies: list[FakeMsg] = []
        self.deleted = False
        self.edits: list[str] = []
        self.reply_markup = None

    async def reply_text(self, text, **kw):
        m = FakeMsg(text, self.chat.id)
        m.reply_markup = kw.get("reply_markup")
        self.replies.append(m)
        return m

    async def edit_text(self, text, **kw):
        self.edits.append(text)
        self.text = text
        self.reply_markup = kw.get("reply_markup", self.reply_markup)

    edit_caption = edit_text

    async def delete(self):
        self.deleted = True

    @property
    def last(self):
        return self.replies[-1].text if self.replies else None


class FakeQuery:
    def __init__(self, data, uid=ADMIN, chat_id=CHAT, message=None):
        self.data = data
        self.from_user = types.SimpleNamespace(id=uid, first_name=f"U{uid}")
        self.message = message or FakeMsg("card", chat_id)
        self.message.id = 55
        self.answers: list[tuple] = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append((text, show_alert))


class FakeApp:
    def __init__(self):
        self.handlers = []
        self.admins = {ADMIN}
        self.sent: list[tuple] = []

    def add_handler(self, h, group=0):
        self.handlers.append(h)

    async def get_chat_member(self, chat_id, user_id):
        st = enums.ChatMemberStatus.ADMINISTRATOR if user_id in self.admins else enums.ChatMemberStatus.MEMBER
        return types.SimpleNamespace(status=st)

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return types.SimpleNamespace(id=900 + len(self.sent))

    async def delete_messages(self, *a, **k):
        pass

    async def get_users(self, ref):
        return types.SimpleNamespace(id=int(ref) if str(ref).lstrip("-").isdigit() else 999, mention=f"@{ref}")


class HandlerAPI(FakeAPI):
    def __init__(self):
        super().__init__()
        self.catalog = {"hello": tr(1, title="Hello"), "bye": tr(2, title="Bye")}
        self.missing = set()

    async def track(self, ref):
        if ref in self.missing:
            raise NotFound("nope", "not_found", 404)
        return self.catalog.get(ref, tr(7, title=ref))

    async def playlist(self, ref, limit=25):
        return "My list", [tr(i) for i in range(1, 4)]

    async def search(self, q, limit=5):
        return [tr(i) for i in range(1, 4)]

    async def usage(self):
        from SHUBHMUSIC.platforms.Youtube import Usage
        return Usage(plan="p3000", daily_limit=3000, used_today=300, remaining_today=2700)


class Assistants:
    def __init__(self):
        self.error = None
        self.userbots = [object()]
        self.calls = []

    async def ensure_present(self, chat_id):
        self.calls.append(chat_id)
        if self.error:
            raise self.error

    def forget(self, chat_id):
        pass


@pytest.fixture
async def h(store):
    cfg = make_config(OWNER_ID=OWNER, COMMAND_COOLDOWN_SECONDS=0)
    app, api, backend, notifier, assistants = FakeApp(), HandlerAPI(), FakeBackend(), FakeNotifier(), Assistants()
    player = Player(cfg, api, backend, store, notifier)
    player.clock = lambda: 1000.0
    ctx = Ctx(cfg=cfg, app=app, api=api, store=store, player=player, assistants=assistants, cards=None)
    register_all(ctx)
    return types.SimpleNamespace(ctx=ctx, app=app, api=api, backend=backend, notifier=notifier, player=player,
                                 assistants=assistants, store=store, cfg=cfg)


async def run(h, name, text="", **kw):
    msg = FakeMsg(text or f"/{name}", **kw)
    await h.ctx.commands[name](h.app, msg)
    return msg


def test_classify():
    assert classify("hello world") == "search"
    assert classify("https://youtu.be/abc") == "video"
    assert classify("https://www.youtube.com/watch?v=abc&list=PL1") == "video"
    assert classify("https://www.youtube.com/playlist?list=PL1") == "playlist"
    assert classify("https://open.spotify.com/track/1") == "foreign"
    assert classify("https://evil.com/?u=https://youtu.be/x") == "foreign"


async def test_every_documented_command_is_registered(h):
    for name in ("play", "vplay", "playforce", "search", "song", "pause", "resume", "skip", "stop", "seek", "loop",
                 "shuffle", "volume", "queue", "now", "like", "playlist", "settings", "auth", "unauth", "help",
                 "ping", "start", "stats", "usage", "broadcast", "ban", "unban", "sudo", "unsudo", "remove", "move", "clear"):
        assert name in h.ctx.commands, name


async def test_play_starts_and_second_song_is_queued(h):
    m = await run(h, "play", "/play hello")
    assert h.assistants.calls == [CHAT]
    assert h.player.queue(CHAT).current.title == "Hello"
    assert m.replies[0].deleted  # the "Searching…" message is removed
    m2 = await run(h, "play", "/play bye", uid=OTHER)
    assert "Bye" in m2.replies[0].edits[-1]
    assert h.player.queue(CHAT).upcoming[0].title == "Bye"


async def test_play_without_text_shows_usage_and_foreign_link_refused(h):
    assert "What should I play" in (await run(h, "play", "/play")).last
    m = await run(h, "play", "/play https://open.spotify.com/track/1")
    assert "YouTube" in m.last and h.player.queue(CHAT).current is None


async def test_play_uses_the_replied_message(h):
    rep = FakeMsg("https://youtu.be/dQw4w9WgXcQ")
    await run(h, "play", "/play", reply=rep)
    assert h.player.queue(CHAT).current is not None


async def test_play_playlist_queues_all(h):
    m = await run(h, "play", "/play https://www.youtube.com/playlist?list=PLx")
    q = h.player.queue(CHAT)
    assert q.current is not None and len(q.upcoming) == 2
    assert "3 songs" in m.replies[0].edits[-1]


async def test_play_not_found_and_assistant_error_and_limit(h):
    h.api.missing.add("zzz")
    assert "could not find" in (await run(h, "play", "/play zzz")).replies[0].edits[-1]
    h.assistants.error = AssistantError("Make me an admin first")
    assert "Make me an admin" in (await run(h, "play", "/play hello")).replies[0].edits[-1]
    h.assistants.error = None
    h.api.limit_after = 0
    m = await run(h, "play", "/play hello")
    assert h.notifier.events[-1][0] == "limit"
    assert h.player.queue(CHAT).current is None


async def test_play_permissions_admins_only_mode(h):
    await h.store.set_setting(CHAT, "play_mode", "admins")
    denied = await run(h, "play", "/play hello", uid=MEMBER)
    assert "Only admins" in denied.last and h.player.queue(CHAT).current is None
    await run(h, "play", "/play hello", uid=ADMIN)
    assert h.player.queue(CHAT).current is not None


async def test_force_play_needs_control_rights(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    denied = await run(h, "playforce", "/playforce bye", uid=MEMBER)
    assert "Only admins" in denied.last and h.player.queue(CHAT).current.title == "Hello"
    await run(h, "playforce", "/playforce bye", uid=ADMIN)
    assert h.player.queue(CHAT).current.title == "Bye"


async def test_anonymous_admin_may_control_but_not_owner_commands(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    anon = types.SimpleNamespace(id=CHAT)
    m = await run(h, "pause", uid=None, sender_chat=anon)
    assert "Paused" in m.last
    m = await run(h, "sudo", "/sudo 5", uid=None, sender_chat=anon)
    assert "Only the bot owner" in m.last


async def test_controls_gated_for_members_and_open_when_everyone(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    assert "Only admins" in (await run(h, "skip", uid=MEMBER)).last
    assert "Only admins" in (await run(h, "stop", uid=MEMBER)).last
    await h.store.set_setting(CHAT, "control_mode", "everyone")
    assert "Paused" in (await run(h, "pause", uid=MEMBER)).last
    assert "Resumed" in (await run(h, "resume", uid=MEMBER)).last


async def test_auth_user_can_control_and_unauth_removes(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    assert "Only admins" in (await run(h, "pause", uid=MEMBER)).last
    await run(h, "auth", f"/auth {MEMBER}", uid=ADMIN)
    assert "Paused" in (await run(h, "pause", uid=MEMBER)).last
    await run(h, "unauth", f"/unauth {MEMBER}", uid=ADMIN)
    assert "Only admins" in (await run(h, "resume", uid=MEMBER)).last
    assert "group admins" in (await run(h, "auth", f"/auth {OTHER}", uid=MEMBER)).last


async def test_nothing_playing_messages(h):
    for cmd in ("pause", "resume", "skip", "loop", "shuffle", "volume", "seek"):
        assert "Nothing is playing" in (await run(h, cmd, uid=ADMIN)).last, cmd
    assert "empty" in (await run(h, "queue")).last


async def test_skip_loop_shuffle_volume_seek_flow(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    await run(h, "play", "/play bye", uid=ADMIN)
    assert "Loop" in (await run(h, "loop", "/loop queue", uid=ADMIN)).last
    assert h.player.queue(CHAT).loop == "queue"
    assert "Use" in (await run(h, "loop", "/loop banana", uid=ADMIN)).last
    assert "Add at least two" in (await run(h, "shuffle", uid=ADMIN)).last
    assert "Volume set to <b>150%" in (await run(h, "volume", "/volume 150", uid=ADMIN)).last
    assert ("volume", CHAT, 150) in h.backend.calls
    assert "Volume set to <b>200%" in (await run(h, "volume", "/volume 999", uid=ADMIN)).last
    assert "Jumped" in (await run(h, "seek", "/seek 1:00", uid=ADMIN)).last
    assert h.backend.calls[-1][-1] == 60  # replayed from 60s
    assert "Use" in (await run(h, "seek", "/seek abc", uid=ADMIN)).last
    assert "can't jump" in (await run(h, "seek", "/seek 9:59", uid=ADMIN)).last
    assert "Skipped" in (await run(h, "skip", uid=ADMIN)).last
    assert h.player.queue(CHAT).current.title == "Bye"


async def test_stop_clears_and_leaves(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    assert "Stopped" in (await run(h, "stop", uid=ADMIN)).last
    assert ("stop", CHAT) in h.backend.calls and h.player.queue(CHAT).current is None
    assert "Nothing is playing" in (await run(h, "stop", uid=ADMIN)).last


async def test_queue_edit_commands(h):
    await run(h, "play", "/play https://www.youtube.com/playlist?list=PLx", uid=ADMIN)
    assert "Removed" in (await run(h, "remove", "/remove 1", uid=ADMIN)).last
    assert "no song" in (await run(h, "remove", "/remove 9", uid=ADMIN)).last
    assert "Moved" not in (await run(h, "move", "/move 5 1", uid=ADMIN)).last
    assert "Removed 1" in (await run(h, "clear", uid=ADMIN)).last


async def test_player_buttons_permission_and_actions(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    cb = h.ctx.callbacks["pl"]
    q = FakeQuery("pl:pause", uid=MEMBER)
    await cb(h.app, q)
    assert q.answers[-1][1] is True and not h.player.queue(CHAT).paused
    q = FakeQuery("pl:pause", uid=ADMIN)
    await cb(h.app, q)
    assert h.player.queue(CHAT).paused and "Paused" in q.answers[-1][0]
    q = FakeQuery("pl:pause", uid=ADMIN)
    await cb(h.app, q)
    assert not h.player.queue(CHAT).paused
    q = FakeQuery("pl:loop", uid=ADMIN)
    await cb(h.app, q)
    assert h.player.queue(CHAT).loop != "off"
    q = FakeQuery("pl:vup", uid=ADMIN)
    await cb(h.app, q)
    assert h.player.queue(CHAT).volume > 100
    q = FakeQuery("pl:save", uid=MEMBER)  # anyone can save
    await cb(h.app, q)
    assert "Saved" in q.answers[-1][0]
    q = FakeQuery("pl:save", uid=MEMBER)
    await cb(h.app, q)
    assert "Already" in q.answers[-1][0]
    q = FakeQuery("pl:stop", uid=ADMIN)
    await cb(h.app, q)
    assert h.player.queue(CHAT).current is None
    q = FakeQuery("pl:skip", uid=ADMIN)
    await cb(h.app, q)
    assert "Nothing is playing" in q.answers[-1][0]


async def test_banned_user_and_chat_are_ignored(h):
    msg = FakeMsg("/play hello", uid=MEMBER)
    assert await h.ctx.admit(msg)
    await h.store.ban_user(MEMBER)
    assert not await h.ctx.admit(FakeMsg("/play hello", uid=MEMBER))
    assert await h.ctx.admit(FakeMsg("/play hello", uid=OWNER))
    await h.store.ban_chat(-5)
    assert not await h.ctx.admit(FakeMsg("/play x", chat_id=-5, uid=OTHER))
    # the registered wrapper (not the bare function) silently drops banned users' button taps
    from pyrogram.handlers import CallbackQueryHandler
    wrapper = [x.callback for x in h.app.handlers if isinstance(x, CallbackQueryHandler)][0]
    await run(h, "play", "/play hello", uid=ADMIN)
    q = FakeQuery("pl:pause", uid=MEMBER)
    await wrapper(h.app, q)
    await h.store.ban_user(ADMIN)
    q = FakeQuery("pl:pause", uid=ADMIN)
    await wrapper(h.app, q)
    assert q.answers == [(None, False)] and not h.player.queue(CHAT).paused


async def test_cooldown_blocks_rapid_repeats(h):
    h.ctx.cfg = make_config(OWNER_ID=OWNER, COMMAND_COOLDOWN_SECONDS=100)
    assert await h.ctx.admit(FakeMsg("/a", uid=OTHER))
    assert not await h.ctx.admit(FakeMsg("/a", uid=OTHER))
    assert await h.ctx.admit(FakeMsg("/a", uid=OWNER + 1))


async def test_owner_commands(h):
    assert "Only the bot owner" in (await run(h, "broadcast", "/broadcast hi", uid=MEMBER, ctype=enums.ChatType.PRIVATE, chat_id=MEMBER)).last
    assert "Only the bot owner" in (await run(h, "stats", uid=MEMBER)).last
    st = await run(h, "stats", uid=OWNER)
    assert "Bot stats" in st.last
    us = await run(h, "usage", uid=OWNER)
    assert "p3000" in us.last and "300" in us.last
    await h.store.touch_chat(-77)
    await h.store.touch_user(5)
    await h.store.ban_chat(-78)
    await h.store.touch_chat(-78)
    m = await run(h, "broadcast", "/broadcast -groups hello all", uid=OWNER)
    sent_to = [c for c, _ in h.app.sent]
    assert -77 in sent_to and -78 not in sent_to and 5 not in sent_to
    assert "Delivered" in m.replies[0].edits[-1]


async def test_ban_and_sudo_rules(h):
    assert "will not ban" in (await run(h, "ban", f"/ban {OWNER}", uid=OWNER)).last
    await run(h, "ban", "/ban 555", uid=OWNER)
    assert await h.store.is_user_banned(555)
    await run(h, "unban", "/unban 555", uid=OWNER)
    assert not await h.store.is_user_banned(555)
    await run(h, "sudo", "/sudo 666", uid=OWNER)
    assert await h.store.is_sudo(666)
    assert "Only the bot owner" in (await run(h, "sudo", "/sudo 777", uid=666)).last  # sudo cannot mint sudo
    await run(h, "ban", "/ban 888", uid=666)  # but sudo can ban
    assert await h.store.is_user_banned(888)
    assert "will not ban" in (await run(h, "ban", "/ban 666", uid=OWNER)).last
    await run(h, "ban", "/ban -4242", uid=OWNER)
    assert await h.store.is_chat_banned(-4242)


async def test_settings_buttons_admin_only(h):
    cb = h.ctx.callbacks["st"]
    q = FakeQuery("st:play", uid=MEMBER)
    await cb(h.app, q)
    assert q.answers[-1][1] is True and (await h.store.settings(CHAT))["play_mode"] == "everyone"
    q = FakeQuery("st:play", uid=ADMIN)
    await cb(h.app, q)
    assert (await h.store.settings(CHAT))["play_mode"] == "admins"
    q = FakeQuery("st:control", uid=ADMIN)
    await cb(h.app, q)
    assert (await h.store.settings(CHAT))["control_mode"] == "everyone"
    assert "Only group admins" in (await run(h, "settings", uid=MEMBER)).last


async def test_like_and_playlist_commands(h):
    await run(h, "play", "/play hello", uid=ADMIN)
    m = await run(h, "like", uid=MEMBER)
    assert "playlist" in m.last.lower()
    assert len(await h.store.playlist_list(MEMBER)) == 1
    pm = await run(h, "playlist", uid=MEMBER)
    assert "Hello" in pm.last or pm.last


# ── search picker ─────────────────────────────────────────────────────────
async def test_search_pick_flow_and_ownership(h):
    m = await run(h, "search", "/search hello", uid=MEMBER)
    assert "Results for" in m.last and m.replies[0].reply_markup is not None
    token = next(iter(h.ctx.search_cache))
    cb = h.ctx.callbacks["sr"]
    other = FakeQuery(f"sr:{token}:0", uid=OTHER)
    await cb(h.app, other)
    assert "Only the person who searched" in other.answers[-1][0] and h.player.queue(CHAT).current is None
    mine = FakeQuery(f"sr:{token}:1", uid=MEMBER)
    await cb(h.app, mine)
    assert h.player.queue(CHAT).current.title == "Song 2"
    again = FakeQuery(f"sr:{token}:1", uid=MEMBER)
    await cb(h.app, again)
    assert "expired" in again.answers[-1][0]  # one pick per search: no double adds


async def test_search_pick_respects_admin_only_mode(h):
    await h.store.set_setting(CHAT, "play_mode", "admins")
    await h.store.touch_chat(CHAT)
    m = await run(h, "search", "/search hello", uid=ADMIN)
    token = next(iter(h.ctx.search_cache))
    h.ctx.search_cache[token] = (MEMBER, h.ctx.search_cache[token][1], h.ctx.search_cache[token][2])
    q = FakeQuery(f"sr:{token}:0", uid=MEMBER)
    await h.ctx.callbacks["sr"](h.app, q)
    assert q.answers[-1][1] is True and h.player.queue(CHAT).current is None
    assert "Only admins" in (await run(h, "search", "/search x", uid=MEMBER)).last


# ── /song: real ffmpeg conversion ─────────────────────────────────────────
async def test_song_download_converts_to_mp3(h, tmp_path):
    import subprocess

    import httpx

    wav = tmp_path / "t.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], check=True)
    payload = wav.read_bytes()
    h.api.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload)))
    sent = {}

    class Client:
        async def send_audio(self, chat_id, path, **kw):
            import os
            sent["size"] = os.path.getsize(path)
            sent["magic"] = open(path, "rb").read(3)
            sent["kw"] = kw

    msg = FakeMsg("/song hello", uid=MEMBER, chat_id=MEMBER, ctype=enums.ChatType.PRIVATE)
    await h.ctx.commands["song"](Client(), msg)
    assert sent["size"] > 1000 and sent["magic"] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    assert sent["kw"]["title"] == "Hello" and msg.replies[0].deleted
    import glob, tempfile
    assert not glob.glob(tempfile.gettempdir() + "/song_*")  # temp files cleaned up


async def test_song_refuses_oversized_download(h):
    import httpx

    h.api.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * (6 * 1024 * 1024))))
    h.ctx.cfg = make_config(OWNER_ID=OWNER, SONG_MAX_MB=5, COMMAND_COOLDOWN_SECONDS=0)

    class Client:
        async def send_audio(self, *a, **k):
            raise AssertionError("must not upload")

    msg = FakeMsg("/song hello", uid=MEMBER)
    # handlers captured cfg at registration; re-register with the small limit
    h.ctx.commands.clear()
    register_all(h.ctx)
    await h.ctx.commands["song"](Client(), msg)
    assert "too large" in msg.replies[0].edits[-1]


async def test_playlist_play_button_queues_everything(h):
    for i in (1, 2, 3):
        await h.store.playlist_add(MEMBER, tr(i))
    q = FakeQuery("pm:play", uid=MEMBER)
    await h.ctx.callbacks["pm"](h.app, q)
    pq = h.player.queue(CHAT)
    assert pq.current.title == "Song 1" and len(pq.upcoming) == 2
    q = FakeQuery("pm:clear", uid=MEMBER)
    await h.ctx.callbacks["pm"](h.app, q)
    assert await h.store.playlist_list(MEMBER) == []


async def test_handlers_register_on_a_real_pyrogram_client(store):
    """Catches typos in filters / handler classes that the fake app would accept."""
    from pyrogram import Client

    cfg = make_config(OWNER_ID=OWNER)
    app = Client("t", api_id=1, api_hash="h", bot_token="1:t", in_memory=True)
    api, backend, notifier = HandlerAPI(), FakeBackend(), FakeNotifier()
    player = Player(cfg, api, backend, store, notifier)
    ctx = Ctx(cfg=cfg, app=app, api=api, store=store, player=player, assistants=Assistants(), cards=None)
    register_all(ctx)
    await asyncio.sleep(0.2)  # pyrogram registers handlers on its loop
    assert sum(len(v) for v in app.dispatcher.groups.values()) > 40
