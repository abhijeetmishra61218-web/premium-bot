"""
Run this ONCE to get custom emoji document IDs.
HOW TO USE:
1. Open Telegram, go to any chat (even Saved Messages)
2. Send a message using custom animated emojis (the ones you want in your buttons)
3. Note the message ID that gets printed
4. Run: python get_emoji_ids.py
5. Copy the IDs you need into bot.py
"""

from telethon import TelegramClient
from telethon.tl.types import MessageEntityCustomEmoji

# Get these from https://my.telegram.org/apps
API_ID = 123456        # <-- replace with your API ID
API_HASH = "your_api_hash"  # <-- replace with your API hash
PHONE = "+91XXXXXXXXXX"     # <-- your phone number

# The chat where you sent the emoji message (use "me" for Saved Messages)
CHAT = "me"

# How many recent messages to scan
LIMIT = 20

async def main():
    async with TelegramClient("emoji_session", API_ID, API_HASH) as client:
        await client.start(phone=PHONE)
        print("Connected! Scanning your last", LIMIT, "messages in", CHAT)
        print("-" * 50)
        async for msg in client.iter_messages(CHAT, limit=LIMIT):
            if not msg.entities:
                continue
            for ent in msg.entities:
                if isinstance(ent, MessageEntityCustomEmoji):
                    # Extract the emoji character this entity covers
                    emoji_char = msg.text[ent.offset: ent.offset + ent.length]
                    print(f"Emoji: {emoji_char}  →  document_id: {ent.document_id}")

import asyncio
asyncio.run(main())