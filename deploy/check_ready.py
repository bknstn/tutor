"""Read-only preflight; never print tokens or send Telegram messages."""
import asyncio
import os

from dotenv import dotenv_values


async def main():
    from telegram import Bot
    values = dotenv_values('/home/hermes/.hermes-tutor/.env')
    original = dotenv_values('/home/hermes/.hermes/.env')
    token = values.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('Missing tutor TELEGRAM_BOT_TOKEN')
    if token == original.get('TELEGRAM_BOT_TOKEN'):
        raise SystemExit('Tutor must use a DIFFERENT Telegram bot')
    if not values.get('TUTOR_OWNER_ID', '').isdigit():
        raise SystemExit('Missing numeric TUTOR_OWNER_ID')
    async with Bot(token) as bot:
        me = await bot.get_me()
        hook = await bot.get_webhook_info()
        if hook.url:
            raise SystemExit('Tutor bot has an existing webhook; resolve before polling')
        print(f'Tutor Telegram bot verified: @{me.username}')


if __name__ == '__main__':
    asyncio.run(main())
