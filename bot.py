import asyncio
import base64
import logging
import os
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup
from openai import OpenAI

IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
IMAGE_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")

COLORING_PROMPT = """
Convert the uploaded photo into a clean black-and-white printable coloring book page for children.

Strict requirements:
- use only clear black outlines on a pure white background
- no colors
- no grayscale fills
- no shadows
- no realistic photo texture
- no text, no watermark, no logo
- keep the main subject recognizable
- simplify small details into large coloring areas
- make it look like a professional children's coloring page ready for printing
""".strip()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать раскраску")],
            [KeyboardButton(text="Мои работы"), KeyboardButton(text="Купить Premium")],
            [KeyboardButton(text="Поддержка")],
        ],
        resize_keyboard=True,
    )


def get_telegram_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN")
    if not token:
        raise RuntimeError("BOT TOKEN NOT FOUND. Add BOT_TOKEN or TELEGRAM_BOT_TOKEN to Bothost variables.")
    return token


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY NOT FOUND. Add OPENAI_API_KEY to Bothost variables.")
    return OpenAI(api_key=api_key)


def generate_coloring_page(image_bytes: bytes) -> bytes:
    client = get_openai_client()

    source_image = BytesIO(image_bytes)
    source_image.name = "source.png"

    result = client.images.edit(
        model=IMAGE_MODEL,
        image=source_image,
        prompt=COLORING_PROMPT,
        size=IMAGE_SIZE,
        n=1,
    )

    if not result.data or not result.data[0].b64_json:
        raise RuntimeError("OpenAI did not return image data")

    return base64.b64decode(result.data[0].b64_json)


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(get_telegram_token())
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Я делаю раскраски из фотографий.\n\n"
            "Нажмите «Создать раскраску» и отправьте фото.",
            reply_markup=main_menu(),
        )

    @dp.message(F.text == "Создать раскраску")
    async def create(message: Message) -> None:
        await message.answer("Пришлите фото JPEG, PNG или WEBP. Я превращу его в раскраску.")

    @dp.message(F.photo)
    async def handle_photo(message: Message) -> None:
        status_message = await message.answer("🎨 Создаю раскраску через GPT Image Mini... Это может занять до минуты.")

        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            downloaded = await bot.download_file(file.file_path)
            source_bytes = downloaded.read()

            result_bytes = await asyncio.to_thread(generate_coloring_page, source_bytes)
            output = BufferedInputFile(result_bytes, filename="raskraska.png")

            await message.answer_photo(
                output,
                caption="Готово! Вот ваша раскраска 🖍️",
                reply_markup=main_menu(),
            )
            await status_message.delete()
        except Exception as exc:
            logging.exception("Failed to generate coloring page")
            await status_message.edit_text(
                "Не получилось создать раскраску.\n\n"
                f"Ошибка: {exc}\n\n"
                "Проверьте OPENAI_API_KEY, баланс OpenAI и доступность модели gpt-image-1-mini."
            )

    @dp.message(F.document)
    async def handle_document(message: Message) -> None:
        await message.answer("Пока лучше отправляйте изображение как обычное фото, не как файл.")

    @dp.message(F.text == "Мои работы")
    async def works(message: Message) -> None:
        await message.answer("История работ появится позже. Сейчас тестируем генерацию раскрасок.")

    @dp.message(F.text == "Купить Premium")
    async def premium(message: Message) -> None:
        await message.answer("Premium добавим после теста генерации. Сейчас работает базовая раскраска.")

    @dp.message(F.text == "Поддержка")
    async def support(message: Message) -> None:
        await message.answer("Напишите ваш вопрос одним сообщением.")

    @dp.message()
    async def fallback(message: Message) -> None:
        await message.answer("Нажмите «Создать раскраску» и отправьте фото.", reply_markup=main_menu())

    me = await bot.get_me()
    logging.info("Bot started @%s with image model %s", me.username, IMAGE_MODEL)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
