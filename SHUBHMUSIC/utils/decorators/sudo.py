"""Guards and helpers for owner / sudo commands."""

from __future__ import annotations

from SHUBHMUSIC.utils.extraction import resolve_user


async def power(ctx, message) -> bool:
    """Owner or sudo user."""
    if message.from_user and await ctx.is_power(message.from_user.id):
        return True
    await message.reply_text("👑 Only the bot owner can use this.")
    return False


async def owner_only(ctx, message) -> bool:
    return await ctx.require(message, "owner")


async def target_id(ctx, message):
    """A user (reply / @username / ID) or a group (negative numeric ID) to act on."""
    user = await resolve_user(ctx, message)
    if user is not None:
        return user.id
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        return int(parts[1])
    return None
