import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Создать раскраску')],[KeyboardButton(text='Мои работы'), KeyboardButton(text='Купить Premium')],[KeyboardButton(text='Поддержка')]], resize_keyboard=True)


async def run_bot() -> None:
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('BOT_TOKEN') or os.environ.get('TOKEN')
    if not token:
        raise RuntimeError('BOT TOKEN NOT FOUND')

    logging.basicConfig(level=logging.INFO)
    bot = Bot(token)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message):
        await message.answer('Загрузите фото, и я превращу его в раскраску.', reply_markup=main_menu())

    @dp.message(F.text == 'Создать раскраску')
    async def create(message: Message):
        await message.answer('Пришлите JPEG, PNG или WEBP до 20 МБ.')

    me = await bot.get_me()
    logging.info('Bot started @%s', me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(run_bot())
