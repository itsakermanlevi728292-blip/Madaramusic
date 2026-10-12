from strings import HELP, HOW, start_text
from SHUBHMUSIC.utils.inline.help import help_back, help_main
from SHUBHMUSIC.utils.inline.start import start_panel

MAIN = "📖 <b>Commands</b>\nPick a topic:"


def register(ctx):
    cfg = ctx.cfg

    @ctx.command("help", group_only=False)
    async def help_cmd(client, message):
        await message.reply_text(MAIN, reply_markup=help_main())

    @ctx.callback("hp")
    async def help_cb(client, query):
        action = query.data.split(":", 1)[1]
        msg = query.message
        if action == "close":
            await msg.delete()
            return await query.answer()
        if action == "home":
            body, markup = start_text(cfg.bot_name), start_panel(ctx.bot_username, cfg.support_chat, cfg.support_channel)
        elif action == "main":
            body, markup = MAIN, help_main()
        elif action == "how":
            body, markup = HOW, help_back()
        elif action in HELP:
            body, markup = HELP[action], help_back()
        else:
            return await query.answer()
        if msg.photo:
            await msg.edit_caption(body, reply_markup=markup)
        else:
            await msg.edit_text(body, reply_markup=markup)
        await query.answer()
