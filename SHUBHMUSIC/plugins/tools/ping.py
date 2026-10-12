import time


def register(ctx):
    @ctx.command("ping", group_only=False)
    async def ping(client, message):
        t0 = time.perf_counter()
        sent = await message.reply_text("🏓 …")
        tg_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        ok = await ctx.api.health()
        api_ms = (time.perf_counter() - t1) * 1000
        up = int(time.time() - ctx.started_at)
        d, rem = divmod(up, 86400)
        h, rem = divmod(rem, 3600)
        await sent.edit_text(
            f"🏓 <b>Pong</b>\nTelegram: <code>{tg_ms:.0f} ms</code>\n"
            f"Music server: {'🟢' if ok else '🔴'} <code>{api_ms:.0f} ms</code>\n"
            f"Uptime: <code>{d}d {h}h {rem // 60}m</code>"
        )
