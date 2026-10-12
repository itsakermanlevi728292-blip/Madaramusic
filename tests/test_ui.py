"""Coloured buttons, copy-link button, expandable quotes, and the repo layout."""

import os

import pytest
from pyrogram import Client, enums
from pyrogram.parser.html import HTML

import strings
from SHUBHMUSIC.utils import formatters
from SHUBHMUSIC.utils.inline.help import help_back, help_main
from SHUBHMUSIC.utils.inline.play import player_markup
from SHUBHMUSIC.utils.inline.playlist import playlist_markup
from SHUBHMUSIC.utils.inline.queue import queue_markup
from SHUBHMUSIC.utils.inline.settings import settings_markup
from SHUBHMUSIC.utils.inline.song import search_markup
from SHUBHMUSIC.utils.inline.start import start_panel
from SHUBHMUSIC.utils.stream.queue import ChatQueue

from .conftest import tr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def playing_queue(n=4, **kw):
    q = ChatQueue(1)
    for i in range(1, n + 1):
        q.add(tr(i, **kw))
    q.advance(manual=True)
    return q


def all_markups():
    q = playing_queue(link="https://www.youtube.com/watch?v=abc")
    return [
        player_markup(q), queue_markup(1, 3), help_main(), help_back(), playlist_markup(3), playlist_markup(0),
        settings_markup({"play_mode": "admins", "control_mode": "everyone", "clean_commands": True}),
        search_markup("abcd1234", [tr(1), tr(2)]), start_panel("MyBot", "https://t.me/chat", "https://t.me/chan"),
    ]


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_no_premium_emoji_anywhere():
    for m in all_markups():
        for b in buttons(m):
            assert not b.icon_custom_emoji_id, b.text


def test_every_button_is_valid_for_telegram():
    for m in all_markups():
        for b in buttons(m):
            assert b.text.strip()
            assert bool(b.callback_data) + bool(b.url) + bool(b.copy_text) == 1, b.text
            if b.callback_data:
                assert len(b.callback_data.encode()) <= 64


def style_of(markup, label):
    return next(b.style for b in buttons(markup) if label in b.text)


def test_player_colours_follow_the_state():
    q = playing_queue()
    m = player_markup(q)
    assert style_of(m, "Pause") == enums.ButtonStyle.PRIMARY
    assert style_of(m, "Stop") == enums.ButtonStyle.DANGER
    assert style_of(m, "Save") == enums.ButtonStyle.SUCCESS
    assert style_of(m, "Loop") == enums.ButtonStyle.DEFAULT
    q.mark_paused()
    q.loop = "queue"
    m = player_markup(q)
    assert style_of(m, "Resume") == enums.ButtonStyle.SUCCESS
    assert style_of(m, "Loop") == enums.ButtonStyle.SUCCESS


def test_player_has_copy_link_button_only_when_there_is_a_link():
    with_link = player_markup(playing_queue(link="https://www.youtube.com/watch?v=abc"))
    copy = [b for b in buttons(with_link) if b.copy_text]
    assert len(copy) == 1 and copy[0].copy_text.text.endswith("v=abc")
    assert not [b for b in buttons(player_markup(playing_queue(link=""))) if b.copy_text]


def test_settings_colours_show_on_and_off():
    m = settings_markup({"play_mode": "admins", "control_mode": "everyone", "clean_commands": True})
    assert style_of(m, "Who can play") == enums.ButtonStyle.DANGER
    assert style_of(m, "Who can control") == enums.ButtonStyle.SUCCESS
    assert style_of(m, "Delete commands") == enums.ButtonStyle.SUCCESS


async def test_styles_reach_the_telegram_wire_format():
    c = Client("t", api_id=1, api_hash="h", bot_token="1:t", in_memory=True)
    raw = await next(b for b in buttons(player_markup(playing_queue())) if "Stop" in b.text).write(c)
    assert raw.style.bg_danger and not raw.style.bg_success


async def test_queue_uses_an_expandable_quote_and_all_texts_parse():
    c = Client("t", api_id=1, api_hash="h", bot_token="1:t", in_memory=True)
    body, _ = formatters.queue_page(playing_queue(), 0)
    parsed = await HTML(c).parse(body)
    quotes = [e for e in parsed["entities"] if type(e).__name__ == "MessageEntityBlockquote"]
    assert quotes and quotes[0].collapsed
    for text in [*strings.HELP.values(), strings.HOW, strings.WELCOME, strings.start_text("Shubh <Music>"),
                 formatters.now_playing(playing_queue(), "x"), formatters.limit_message(3600)]:
        await HTML(c).parse(text)  # raises on broken HTML


def test_repo_layout_matches_the_reference_structure():
    must_exist = [
        "config.py", "sample.env", "requirements.txt", "Dockerfile", "Procfile", "start", "runtime.txt", "heroku.yml",
        "strings/__init__.py", "LICENSE", "README.md",
        "SHUBHMUSIC/__main__.py", "SHUBHMUSIC/logging.py",
        "SHUBHMUSIC/platforms/Youtube.py",
        "SHUBHMUSIC/core/bot.py", "SHUBHMUSIC/core/call.py", "SHUBHMUSIC/core/userbot.py",
        "SHUBHMUSIC/plugins/play/play.py", "SHUBHMUSIC/plugins/admins/skip.py", "SHUBHMUSIC/plugins/bot/start.py",
        "SHUBHMUSIC/plugins/sudo/broadcast.py", "SHUBHMUSIC/plugins/tools/song.py",
        "SHUBHMUSIC/utils/database.py", "SHUBHMUSIC/utils/thumbnails.py", "SHUBHMUSIC/utils/inline/play.py",
    ]
    missing = [p for p in must_exist if not os.path.exists(os.path.join(ROOT, p))]
    assert not missing, missing


def test_repo_has_no_secrets_or_cookies():
    banned = ["cookies.txt", ".env", "data"]
    assert not [b for b in banned if os.path.exists(os.path.join(ROOT, b))]
