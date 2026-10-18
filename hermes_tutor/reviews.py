"""One Telegram message per review, with explicit consent between batches."""
from .store import REVIEW_LIMIT, Store


def review_content(batch):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from . import format_card

    def button(label, action):
        return InlineKeyboardButton(label, callback_data=f'tutorq:{batch["token"]}:{batch["revision"]}:{action}')

    buttons = []
    if batch['state'] == 'active':
        card = batch['card']
        text = f'Повторение · {batch["done"] + 1}/{batch["total"]}\n\n'
        if card['revealed']:
            text += format_card(card)
            buttons.append([button('Again · 1 дн.', 'again'), button('Good · 3 дн.', 'good'),
                            button('Easy · 7 дн.', 'easy')])
        else:
            text += f'Что значит «{card["term"]}»?'
            buttons.append([button('Показать ответ', 'show')])
        buttons.append([button('На сегодня всё', 'stop')])
    elif batch['state'] == 'complete':
        text = f'Готово! Повторено {batch["done"]} из {batch["total"]} карточек.'
        if batch['more']:
            text += '\n\nЕсть ещё слова для повторения. Продолжить?'
            buttons.append([button(f'Продолжить · до {REVIEW_LIMIT} карточек', 'more'),
                            button('На сегодня всё', 'stop')])
        else:
            text += '\nНа сегодня больше нет слов для повторения.'
    else:
        text = f'На сегодня всё. Повторено {batch["done"]} из {batch["total"]} карточек.\nПродолжить позже: /review.'
    return dict(text=text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)


async def edit_review(edit, batch, **kwargs):
    from telegram.error import BadRequest
    try:
        await edit(**kwargs, **review_content(batch))
    except BadRequest as exc:
        if 'message is not modified' not in str(exc).lower():
            raise


async def send_reviews(bot, chat_id, store=None, scheduled=False):
    """Return cards offered, zero when none are due, or None for an existing panel."""
    store = store or Store()
    batch = store.start_review(chat_id, scheduled=scheduled)
    if not batch:
        return 0
    if not batch['created']:
        if not scheduled and batch['message_id'] is not None:
            await edit_review(bot.edit_message_text, batch, chat_id=chat_id, message_id=batch['message_id'])
        return None
    try:
        msg = await bot.send_message(chat_id=chat_id, **review_content(batch))
        store.deliver_review(batch['token'], msg.message_id)
    except Exception:
        store.abandon_review(batch['token'])
        raise
    return batch['total']
