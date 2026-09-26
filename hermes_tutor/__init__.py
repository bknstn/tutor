"""Hermes native plugin: vocabulary tools and Telegram review callbacks."""
import json
import logging
import os

from .store import INTERVALS, Store, TYPES

log = logging.getLogger(__name__)


def tool(args, **kwargs):
    try:
        data = dict(args)
        action = data.pop('action')
        store = Store()
        if action == 'lookup':
            result = {'card': store.lookup(data['term'])}
        elif action == 'save':
            result = store.save(**data)
        else:
            raise ValueError('Unknown action')
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        log.warning('Vocabulary operation failed: %s', type(exc).__name__)
        return json.dumps({'error': str(exc) if isinstance(exc, ValueError) else 'Storage operation failed; do not confirm saved.'})


def authorized(update):
    owner = os.environ.get('TUTOR_OWNER_ID', '')
    return bool(owner and update.effective_user and update.effective_chat
                and str(update.effective_user.id) == owner
                and str(update.effective_chat.id) == owner
                and update.effective_chat.type == 'private')


def keyboard(token, revealed=False):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    actions = [('Again', 'again'), ('Good', 'good'), ('Easy', 'easy')] if revealed else [('Показать ответ', 'show')]
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f'tutor:{token}:{action}')
                                  for label, action in actions]])


async def send_reviews(bot, chat_id, store=None):
    store = store or Store()
    cards = store.reserve(chat_id)
    sent = 0
    for card in cards:
        try:
            msg = await bot.send_message(chat_id=chat_id,
                text=f'Quick review\n\nWhat does “{card["term"]}” mean?',
                reply_markup=keyboard(card['token']))
            store.delivered(card['token'], msg.message_id)
            sent += 1
        except Exception:
            # Retry remaining cards on the next run. A network timeout can mean
            # Telegram accepted a message: any orphaned buttons fail closed.
            for remaining in cards[sent:]:
                store.release(remaining['token'])
            raise
    return sent


def wire(application, adapter):
    from telegram.ext import CallbackQueryHandler, CommandHandler

    async def welcome(update, context):
        if authorized(update):
            await update.message.reply_text('Отправь английское слово или короткую фразу. Я объясню, переведу и сохраню.\n\nПовторения: ежедневно в 19:00 по Варшаве, до 5 карточек. /review — повторить сейчас.')

    async def review(update, context):
        if not authorized(update):
            return
        try:
            count = await send_reviews(context.bot, update.effective_chat.id)
            if not count:
                await update.message.reply_text('На сегодня новых повторений нет. Отправь английское слово или фразу.')
        except Exception:
            log.exception('Review delivery failed')
            await update.message.reply_text('Не удалось отправить повторение. Попробуй /review позже.')

    async def button(update, context):
        query = update.callback_query
        if not authorized(update):
            await query.answer('Нет доступа', show_alert=True)
            return
        _, token, action = query.data.split(':')
        card = Store().answer(token, update.effective_chat.id, query.message.message_id, action)
        if not card:
            await query.answer('Эта карточка уже обработана или устарела.')
            return
        await query.answer()
        if action == 'show':
            await query.edit_message_text(
                f'{card["term"]}\n\nMeaning: {card["definition"]}\nRU: {card["translation"]}\n\nExample: {card["example"]}',
                reply_markup=keyboard(token, True))
        else:
            await query.edit_message_text(f'{card["term"]} — {action.title()}\nСледующее повторение через {INTERVALS[action]} дн.')

    application.add_handler(CommandHandler('start', welcome))
    application.add_handler(CommandHandler('review', review))
    application.add_handler(CallbackQueryHandler(button, pattern=r'^tutor:[0-9a-f]{16}:(show|again|good|easy)$'))


def register(ctx):
    properties = {key: {'type': 'string'} for key in ('term', 'definition', 'translation', 'example')}
    properties.update(action={'type': 'string', 'enum': ['lookup', 'save']},
                      type={'type': 'string', 'enum': list(TYPES)})
    ctx.register_tool(name='tutor_vocabulary', toolset='tutor',
        schema={'name': 'tutor_vocabulary',
                'description': 'Look up a vocabulary term before generating a card. Save with term, type, short English definition, Russian translation, and one English example. Only report Saved after status=saved. Scheduling is handled by Telegram buttons, never by this tool.',
                'parameters': {'type': 'object', 'properties': properties, 'required': ['action', 'term']}},
        handler=tool)
    ctx.register_platform_handler('telegram', wire)
