"""Create the STRING_SESSION for the assistant account:  python session.py"""

import asyncio


async def main() -> None:
    from pyrogram import Client

    print("\nThis creates a login string for the ASSISTANT account (use a separate Telegram account, not your main one).")
    print("Get API_ID and API_HASH from https://my.telegram.org\n")
    api_id = int(input("API_ID: ").strip())
    api_hash = input("API_HASH: ").strip()
    async with Client("session-maker", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        string = await app.export_session_string()
        me = await app.get_me()
    print(f"\nLogged in as {me.first_name} (id {me.id}). Your STRING_SESSION is below.")
    print("Keep it secret: anyone with it can use that account.\n")
    print(string)
    print()


if __name__ == "__main__":
    asyncio.run(main())
