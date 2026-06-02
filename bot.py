import asyncio
import logging
import os
from io import BytesIO

import cv2
import numpy as np
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup
from PIL import Image

MAX_IMAGE_SIDE = int(os.environ.get("MAX_IMAGE_SIDE", "1400"))
CANNY_LOW = int(os.environ.get("CANNY_LOW", "45"))
CANNY_HIGH = int(os.environ.get("CANNY_HIGH", "120"))
MIN_CONTOUR_AREA = int(os.environ.get("MIN_CONTOUR_AREA", "70"))
LINE_THICKNESS = int(os.environ.get("LINE_THICKNESS", "1"))


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


def load_image(image_bytes: bytes) -> np.ndarray:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def remove_small_components(binary_edges: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(binary_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    clean = np.zeros_like(binary_edges)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= MIN_CONTOUR_AREA:
            cv2.drawContours(clean, [contour], -1, 255, LINE_THICKNESS)
    return clean


def generate_coloring_page(image_bytes: bytes) -> bytes:
    """Free OpenCV photo-to-coloring conversion. No OpenAI calls, no paid API usage."""
    image = load_image(image_bytes)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Smooth textures but keep main object borders.
    gray = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Improve contrast before edge detection.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)

    # Close gaps in the main outlines, then remove small noise contours.
    kernel_close = np.ones((2, 2), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    edges = remove_small_components(edges)

    # Make lines more visible for coloring.
    kernel_dilate = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel_dilate, iterations=1)

    # Black lines on white background.
    line_art = 255 - edges

    # Very small blur removes jagged pixel noise but keeps printable outlines.
    line_art = cv2.medianBlur(line_art, 3)

    success, encoded = cv2.imencode(".png", line_art)
    if not success:
        raise RuntimeError("Failed to encode PNG")
    return encoded.tobytes()


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
        status_message = await message.answer("🖍️ Делаю раскраску OpenCV-алгоритмом. Это бесплатно...")

        try:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            downloaded = await bot.download_file(file.file_path)
            source_bytes = downloaded.read()

            result_bytes = await asyncio.to_thread(generate_coloring_page, source_bytes)
            output = BufferedInputFile(result_bytes, filename="raskraska.png")

            await message.answer_photo(
                output,
                caption="Готово! Вот бесплатная OpenCV-раскраска 🖍️",
                reply_markup=main_menu(),
            )
            await status_message.delete()
        except Exception as exc:
            logging.exception("Failed to generate local coloring page")
            await status_message.edit_text(
                "Не получилось создать раскраску.\n\n"
                f"Ошибка: {exc}\n\n"
                "Попробуйте отправить другое фото с более чётким объектом и спокойным фоном."
            )

    @dp.message(F.document)
    async def handle_document(message: Message) -> None:
        await message.answer("Пока лучше отправляйте изображение как обычное фото, не как файл.")

    @dp.message(F.text == "Мои работы")
    async def works(message: Message) -> None:
        await message.answer("История работ появится позже. Сейчас работает бесплатная OpenCV-генерация.")

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
    logging.info("Bot started @%s in free OpenCV coloring mode", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
