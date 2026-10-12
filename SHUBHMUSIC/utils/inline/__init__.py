"""Inline keyboards, one file per screen.

Telegram's coloured buttons are used with a simple meaning everywhere:
  blue   (PRIMARY) = navigate / information
  green  (SUCCESS) = start, resume, save, "on"
  red    (DANGER)  = stop, clear, close, "off"
"""

from pyrogram.enums import ButtonStyle
from pyrogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

PRIMARY = ButtonStyle.PRIMARY
SUCCESS = ButtonStyle.SUCCESS
DANGER = ButtonStyle.DANGER
PLAIN = ButtonStyle.DEFAULT


def button(text: str, *, cb: str | None = None, url: str | None = None, copy: str | None = None,
           style: ButtonStyle = PLAIN) -> InlineKeyboardButton:
    """One button. Pass exactly one of cb (callback data), url or copy (text copied on tap)."""
    kw = {"style": style}
    if cb is not None:
        kw["callback_data"] = cb
    elif url is not None:
        kw["url"] = url
    elif copy is not None:
        kw["copy_text"] = CopyTextButton(text=copy[:256])
    else:
        raise ValueError("a button needs cb, url or copy")
    return InlineKeyboardButton(text, **kw)


def markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[b for b in r if b is not None] for r in rows if any(b is not None for b in r)])


def close(prefix: str) -> InlineKeyboardButton:
    return button("✖️ Close", cb=f"{prefix}:close", style=DANGER)
