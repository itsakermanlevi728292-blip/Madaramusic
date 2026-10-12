from pyrogram import enums

from strings import start_text
from SHUBHMUSIC.utils.inline.start import start_panel


def register(ctx):
    cfg = ctx.cfg

    @ctx.command("start", group_only=False)
    async def start(client, message):
        if message.chat.type != enums.ChatType.PRIVATE:
            return await message.reply_text("🎧 I'm ready. Start a voice chat, then send /play and a song name.")
        markup = start_panel(ctx.bot_username, cfg.support_chat, cfg.support_channel)
        body = start_text(cfg.bot_name)
        if cfg.start_image_url:
            try:
                return await message.reply_photo(cfg.start_image_url, caption=body, reply_markup=markup,
                                                 parse_mode=enums.ParseMode.HTML)
            except Exception:
                pass
        await message.reply_text(body, reply_markup=markup)
