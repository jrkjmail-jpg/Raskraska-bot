import asyncio
import logging
import os
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup
from PIL import Image, ImageFilter, ImageOps

MAX_IMAGE_SIDE = int(os.environ.get("MAX_IMAGE_SIDE", "1400"))
EDGE_THRESHOLD = int(os.environ.get("EDGE_THRESHOLD", "32"))


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


def resize_image(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return image


def generate_coloring_page(image_bytes: bytes) -> bytes:
    """Free local photo-to-coloring conversion. No OpenAI calls, no paid API usage."""
    image = Image.open(BytesIO(image_bytes))
    image = resize_image(image)

    gray = ImageOps.grayscale(image)
    smooth = gray.filter(ImageFilter.MedianFilter(size=3))
    smooth = smooth.filter(ImageFilter.SMOOTH_MORE)

    edges = smooth.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)

    # Convert edge map into black outlines on a white background.
    line_art = edges.point(lambda pixel: 0 if pixel > EDGE_THRESHOLD else 255, mode="1")
    line_art = line_art.convert("L")

    # Make outlines a little thicker and cleaner for children's coloring.
    inverted = ImageOps.invert(line_art)
    inverted = inverted.filter(ImageFilter.MaxFilter(size=3))
    line_art = ImageOps.invert(inverted)

    output = BytesIO()
    line_art.save(output, format="PNG", optimize=True)
    return output.getvalue()


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(get_telegram_token())
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "Привет! Я делаю бесплатные раскраски из фотографий.\n\n"
            "Нажмите «Создать раскраску» и отправьте фото.",
            reply_markup=main_menu(),
        )

    @dp.message(F.text == "Создать раскраску")
    async def create(message: Message) -> None:
        await message.answer("Пришлите фото. Я бесплатно превращу его в контурную раскраску.")

    @dp.message(F.photo)
    async def handle_photo(message: Message) -> None:
        status_message = await message.answer("🖍️ Делаю раскраску локально. Это бесплатно и обычно занимает пару секунд...")

        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            downloaded = await bot.download_file(file.file_path)
            source_bytes = downloaded.read()

            result_bytes = await asyncio.to_thread(generate_coloring_page, source_bytes)
            output = BufferedInputFile(result_bytes, filename="raskraska.png")

            await message.answer_photo(
                output,
                caption="Готово! Вот бесплатная раскраска 🖍️",
                reply_markup=main_menu(),
            )
            await status_message.delete()
        except Exception as exc:
            logging.exception("Failed to generate local coloring page")
            await status_message.edit_text(
                "Не получилось создать раскраску.\n\n"
                f"Ошибка: {exc}\n\n"
                "Попробуйте отправить другое фото с более чётким объектом и хорошим светом."
            )

    @dp.message(F.document)
    async def handle_document(message: Message) -> None:
        await message.answer("Пока лучше отправляйте изображение как обычное фото, не как файл.")

    @dp.message(F.text == "Мои работы")
    async def works(message: Message) -> None:
        await message.answer("История работ появится позже. Сейчас работает бесплатная генерация раскрасок.")

    @dp.message(F.text == "Купить Premium")
    async def premium(message: Message) -> None:
        await message.answer("Premium добавим позже: красивые AI-раскраски, PDF и несколько вариантов.")

    @dp.message(F.text == "Поддержка")
    async def support(message: Message) -> None:
        await message.answer("Напишите ваш вопрос одним сообщением.")

    @dp.message()
    async def fallback(message: Message) -> None:
        await message.answer("Нажмите «Создать раскраску» и отправьте фото.", reply_markup=main_menu())

    me = await bot.get_me()
    logging.info("Bot started @%s in free local coloring mode", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
