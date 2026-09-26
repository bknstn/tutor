"""Invoked by the tutor's systemd timer; no LLM required."""
import asyncio
import os

from . import send_reviews


async def main():
    from telegram import Bot
    owner = os.environ['TUTOR_OWNER_ID']
    if not owner.isdigit():
        raise ValueError('TUTOR_OWNER_ID must be a numeric private Telegram user ID')
    async with Bot(os.environ['TELEGRAM_BOT_TOKEN']) as bot:
        count = await send_reviews(bot, owner)
        print(f'Review cards sent: {count}')


if __name__ == '__main__':
    asyncio.run(main())
