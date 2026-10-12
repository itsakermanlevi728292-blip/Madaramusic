"""Find the target user of /auth, /ban...: a reply, an @username or a numeric ID."""

from __future__ import annotations


async def resolve_user(ctx, message):
    rep = getattr(message, "reply_to_message", None)
    if rep is not None and rep.from_user is not None:
        return rep.from_user
    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        return None
    ref = parts[1].strip().split()[0]
    try:
        return await ctx.app.get_users(int(ref) if ref.lstrip("-").isdigit() else ref)
    except Exception:
        return None
