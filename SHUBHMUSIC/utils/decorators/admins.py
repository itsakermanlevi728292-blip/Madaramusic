"""Shared permission guards for the plugins."""

from __future__ import annotations


async def need_active(ctx, message):
    """The chat's queue if something is playing, otherwise replies and returns None."""
    q = ctx.player.queues.get(message.chat.id)
    if q is None or q.current is None:
        await message.reply_text("Nothing is playing right now. Start with /play.")
        return None
    return q


async def gate(ctx, message) -> bool:
    """True if the sender may control the player (admins, authorised users, or everyone if the group allows)."""
    return await ctx.require(message, "control")
