"""Owner / sudo tools: stats, API quota, broadcast, bans, sudo list."""

from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import enums
from pyrogram.errors import FloodWait

from ..api import APIError
from ..ui.text import esc, fmt_time
from .settings import resolve_user

log = logging.getLogger("bot.owner")


def register(ctx):
    store = ctx.store

    async def power(message) -> bool:
        if message.from_user and await ctx.is_power(message.from_user.id):
            return True
        await message.reply_text("👑 Only the bot owner can use this.")
        return False

    async def owner_only(message) -> bool:
        return await ctx.require(message, "owner")

    @ctx.command("stats", group_only=False)
    async def stats(client, message):
        if not await power(message):
            return
        c = await store.counts()
        up = int(time.time() - ctx.started_at)
        await message.reply_text(
            "📊 <b>Bot stats</b>\n"
            f"Groups: <code>{c['chats']}</code>\n"
            f"Users: <code>{c['users']}</code>\n"
            f"Saved playlist songs: <code>{c['playlist_songs']}</code>\n"
            f"Playing right now: <code>{len(ctx.player.active_chats())}</code> group(s)\n"
            f"Assistants: <code>{len(ctx.assistants.userbots)}</code>\n"
            f"Uptime: <code>{fmt_time(up)}</code>"
        )

    @ctx.command("usage", group_only=False)
    async def usage(client, message):
        if not await power(message):
            return
        try:
            u = await ctx.api.usage()
        except APIError as e:
            return await message.reply_text(f"⚠️ Could not read the API plan: {esc(str(e))}")
        bar_used = min(1.0, u.used_today / u.daily_limit) if u.daily_limit else 0
        filled = int(bar_used * 14)
        expires = f"\nPlan ends: <code>{esc(u.plan_expires_at)}</code>" if u.plan_expires_at else ""
        await message.reply_text(
            "🔑 <b>API usage today</b>\n"
            f"Plan: <b>{esc(u.plan)}</b>{expires}\n"
            f"Used: <code>{u.used_today}</code> / <code>{u.daily_limit}</code>\n"
            f"Left: <code>{u.remaining_today}</code>\n"
            f"<code>{'█' * filled}{'░' * (14 - filled)}</code>"
        )

    @ctx.command("broadcast", group_only=False)
    async def broadcast(client, message):
        if not await owner_only(message):
            return
        parts = (message.text or "").split(None, 1)
        flags = ""
        body = parts[1] if len(parts) > 1 else ""
        while body.startswith("-"):
            flag, _, body = body.partition(" ")
            flags += flag
        body = body.strip()
        source = message.reply_to_message
        if not body and source is None:
            return await message.reply_text(
                "Usage: <code>/broadcast [-users] [-groups] text</code>, or reply to a message.\n"
                "With no flag it goes to groups and users.")
        users = "-users" in flags or "-groups" not in flags
        groups = "-groups" in flags or "-users" not in flags
        targets: list[int] = []
        if groups:
            targets += await store.chat_ids()
        if users:
            targets += await store.user_ids()
        banned_users, banned_chats = await store.banned_ids()
        skip = set(banned_users) | set(banned_chats)
        targets = [t for t in dict.fromkeys(targets) if t not in skip]
        status = await message.reply_text(f"📣 Sending to {len(targets)} chats…")
        ok = failed = 0
        for i, target in enumerate(targets, 1):
            try:
                if source is not None:
                    await source.copy(target)
                else:
                    await ctx.app.send_message(target, body, parse_mode=enums.ParseMode.HTML)
                ok += 1
            except FloodWait as e:
                await asyncio.sleep(min(e.value, 60) + 1)
                try:
                    if source is not None:
                        await source.copy(target)
                    else:
                        await ctx.app.send_message(target, body, parse_mode=enums.ParseMode.HTML)
                    ok += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.06)
            if i % 50 == 0:
                try:
                    await status.edit_text(f"📣 Sending… {i}/{len(targets)}")
                except Exception:
                    pass
        await status.edit_text(f"✅ Broadcast finished.\nDelivered: <code>{ok}</code>\nFailed: <code>{failed}</code>")

    async def _target_id(message):
        user = await resolve_user(ctx, message)
        if user is not None:
            return user.id
        parts = (message.text or "").split()
        if len(parts) > 1 and parts[1].lstrip("-").isdigit():
            return int(parts[1])
        return None

    @ctx.command("ban", group_only=False)
    async def ban(client, message):
        if not await power(message):
            return
        target = await _target_id(message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username. For a group, use its numeric ID.")
        if ctx.is_owner(target) or await store.is_sudo(target):
            return await message.reply_text("I will not ban the owner or a sudo user.")
        if target < 0:
            await store.ban_chat(target, True)
            await ctx.player.stop(target)
            return await message.reply_text(f"🚫 Group <code>{target}</code> is banned.")
        await store.ban_user(target, True)
        await message.reply_text(f"🚫 User <code>{target}</code> is banned from the bot.")

    @ctx.command("unban", group_only=False)
    async def unban(client, message):
        if not await power(message):
            return
        target = await _target_id(message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        if target < 0:
            gone = await store.ban_chat(target, False)
        else:
            gone = await store.ban_user(target, False)
        await message.reply_text("✅ Unbanned." if gone else "That one was not banned.")

    @ctx.command("banned", group_only=False)
    async def banned(client, message):
        if not await power(message):
            return
        users, chats = await store.banned_ids()
        if not users and not chats:
            return await message.reply_text("Nobody is banned.")
        lines = [f"👤 <code>{u}</code>" for u in users] + [f"👥 <code>{c}</code>" for c in chats]
        await message.reply_text("🚫 <b>Banned</b>\n" + "\n".join(lines[:60]))

    @ctx.command("sudo", group_only=False)
    async def sudo(client, message):
        if not await owner_only(message):
            return
        target = await _target_id(message)
        if target is None or target < 0:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        added = await store.set_sudo(target, True)
        await message.reply_text(f"✅ <code>{target}</code> is now a sudo user." if added else "Already a sudo user.")

    @ctx.command("unsudo", group_only=False)
    async def unsudo(client, message):
        if not await owner_only(message):
            return
        target = await _target_id(message)
        if target is None:
            return await message.reply_text("Reply to a user or give a user ID / @username.")
        gone = await store.set_sudo(target, False)
        await message.reply_text("🗑 Sudo removed." if gone else "That user was not sudo.")

    @ctx.command("sudolist", group_only=False)
    async def sudolist(client, message):
        if not await power(message):
            return
        ids = sorted(ctx.cfg.owner_ids) + await store.sudo_list()
        lines = [f"👑 <code>{i}</code>" for i in sorted(ctx.cfg.owner_ids)] + [f"🛡 <code>{i}</code>" for i in await store.sudo_list()]
        await message.reply_text("🛡 <b>Owner &amp; sudo</b>\n" + ("\n".join(lines) if ids else "None"))
