import asyncio

from pyrogram import enums
from pyrogram.errors import FloodWait

from SHUBHMUSIC.utils.decorators.sudo import owner_only


def register(ctx):
    store = ctx.store

    async def deliver(source, body, target) -> None:
        if source is not None:
            await source.copy(target)
        else:
            await ctx.app.send_message(target, body, parse_mode=enums.ParseMode.HTML)

    @ctx.command("broadcast", group_only=False)
    async def broadcast(client, message):
        if not await owner_only(ctx, message):
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
                await deliver(source, body, target)
                ok += 1
            except FloodWait as e:
                await asyncio.sleep(min(e.value, 60) + 1)
                try:
                    await deliver(source, body, target)
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
