"""Hermes native plugin: vocabulary tools and Telegram review callbacks."""
import json
import logging
import os

from .store import INTERVALS, Store, TYPES
from .sessions import daily_session

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
        elif action == 'enrich':
            result = store.enrich(**data)
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


def format_card(card):
    header = card['term']
    if card['pronunciation']:
        header += f'\nIPA: {card["pronunciation"]}'
    blocks = []
    for index, meaning in enumerate(card['meanings'], 1):
        label = f'{index}. Meaning' if len(card['meanings']) > 1 else 'Meaning'
        blocks.append(f'{label}: {meaning["definition"]}\nRU: {meaning["translation"]}'
                      f'\nExample: {meaning["example"]}')
    return header + '\n\n' + '\n\n'.join(blocks)


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
                format_card(card),
                reply_markup=keyboard(token, True))
        else:
            await query.edit_message_text(f'{card["term"]} — {action.title()}\nСледующее повторение через {INTERVALS[action]} дн.')

    application.add_handler(CommandHandler('start', welcome))
    application.add_handler(CommandHandler('review', review))
    application.add_handler(CallbackQueryHandler(button, pattern=r'^tutor:[0-9a-f]{16}:(show|again|good|easy)$'))


def register(ctx):
    meaning_fields = {key: {'type': 'string', 'minLength': 1, 'maxLength': 300}
                      for key in ('definition', 'translation', 'example')}
    properties = {
        'term': {'type': 'string'},
        'pronunciation': {'type': 'string', 'minLength': 1, 'maxLength': 160,
                          'description': 'IPA in /slashes/; use standard British pronunciation. Include sense labels for words whose pronunciation depends on meaning.'},
        'meanings': {'type': 'array', 'minItems': 1, 'maxItems': 3,
                     'description': 'Start with one common meaning. Add another only for a genuinely different sense or established domain-specific use. Compare candidates before saving and merge paraphrases, synonyms, broader/narrower descriptions, and process/result variants of the same sense. Different examples or settings alone are not new senses. Reimbursement (money vs repayment process) and curriculum (course content vs subjects offered) each need one meaning; treat (behave towards, give medical care, give something enjoyable) has distinct senses. Keep one when uncertain; never fill a quota. Each meaning has a concise Russian translation and one English example.',
                     'items': {'type': 'object', 'properties': meaning_fields,
                               'required': list(meaning_fields), 'additionalProperties': False}},
    }
    properties.update(action={'type': 'string', 'enum': ['lookup', 'save', 'enrich']},
                      type={'type': 'string', 'enum': list(TYPES)})
    ctx.register_tool(name='tutor_vocabulary', toolset='tutor',
        schema={'name': 'tutor_vocabulary',
                'description': 'Look up a term before generating a card. Save with term, type, pronunciation (IPA), and meanings (1–3 objects with short English definition, Russian translation, and one English example each). Merge semantic duplicates BEFORE calling save/enrich; add a meaning only for a new sense or established domain-specific use, never just another wording or synonym. Prefer one meaning when uncertain. For a legacy card with empty pronunciation, use enrich with term, pronunciation, and meanings to add content while preserving reviews. Display only the returned card and its stored meanings. Only report Saved after status=saved, or Updated after status=enriched. Scheduling is handled by Telegram buttons, never by this tool.',
                'parameters': {'type': 'object', 'properties': properties, 'required': ['action', 'term']}},
        handler=tool)
    ctx.register_platform_handler('telegram', wire)
    ctx.register_hook('pre_gateway_dispatch', daily_session)
