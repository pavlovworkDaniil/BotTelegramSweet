"""Telegram bot for browsing and downloading local movies.

The bot reads files from a local directory and lets users choose a movie from
inline buttons. When a user taps a movie, the bot sends the corresponding file
from disk directly to the chat.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".mpeg",
    ".mpg",
    ".m4v",
}
MAX_TELEGRAM_FILE_SIZE_BYTES = 49 * 1024 * 1024


@dataclass(frozen=True)
class Movie:
    """Movie metadata used by the bot UI."""

    filename: str
    path: Path
    size_bytes: int


def _movies_dir() -> Path:
    return Path(os.getenv("MOVIES_DIR", "./movies")).expanduser().resolve()


def _human_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _scan_movies() -> List[Movie]:
    directory = _movies_dir()
    if not directory.exists() or not directory.is_dir():
        return []

    movies: List[Movie] = []
    for file_path in sorted(directory.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        stat = file_path.stat()
        movies.append(
            Movie(
                filename=file_path.name,
                path=file_path,
                size_bytes=stat.st_size,
            )
        )
    return movies


def _movies_keyboard(movies: List[Movie]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"🎬 {movie.filename}", callback_data=f"movie:{index}")]
        for index, movie in enumerate(movies)
    ]
    buttons.append([InlineKeyboardButton("🔄 Обновить список", callback_data="movies:refresh")])
    return InlineKeyboardMarkup(buttons)


def _movies_text(movies: List[Movie]) -> str:
    if not movies:
        return (
            "Фильмы не найдены.\n"
            f"Проверьте папку: <code>{_movies_dir()}</code>\n"
            "Поддерживаемые форматы: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )

    lines = ["Выберите фильм для скачивания:"]
    for index, movie in enumerate(movies, start=1):
        lines.append(f"{index}. {movie.filename} ({_human_size(movie.size_bytes)})")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    movies = _scan_movies()
    await message.reply_text(
        (
            "Привет! 👋\n"
            "Я бот для скачивания фильмов из локальной папки на сервере.\n"
            "Используйте /movies, чтобы открыть список файлов."
        )
    )
    await message.reply_html(_movies_text(movies), reply_markup=_movies_keyboard(movies))


async def movies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    movies = _scan_movies()
    await message.reply_html(_movies_text(movies), reply_markup=_movies_keyboard(movies))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    text = (
        "Команды:\n"
        "• /start — приветствие и быстрый доступ к фильмам.\n"
        "• /movies — показать список фильмов из папки.\n"
        "• /help — подсказка по командам.\n\n"
        "Настройте переменную окружения <code>MOVIES_DIR</code>, чтобы указать папку с фильмами."
    )
    await message.reply_html(text)


async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""
    movies = _scan_movies()

    if data == "movies:refresh":
        await query.edit_message_text(
            _movies_text(movies),
            reply_markup=_movies_keyboard(movies),
            parse_mode="HTML",
        )
        return

    if not data.startswith("movie:"):
        await query.answer("Неизвестная команда", show_alert=True)
        return

    try:
        movie_index = int(data.split(":", 1)[1])
    except ValueError:
        await query.answer("Некорректный выбор", show_alert=True)
        return

    if movie_index < 0 or movie_index >= len(movies):
        await query.answer("Фильм не найден, обновите список", show_alert=True)
        return

    movie = movies[movie_index]
    if movie.size_bytes > MAX_TELEGRAM_FILE_SIZE_BYTES:
        await query.message.reply_text(
            (
                f"Файл слишком большой для отправки ботом: {movie.filename}\n"
                f"Размер: {_human_size(movie.size_bytes)}\n"
                f"Лимит: {_human_size(MAX_TELEGRAM_FILE_SIZE_BYTES)}"
            )
        )
        return

    if not movie.path.exists():
        await query.message.reply_text("Файл не найден на диске. Нажмите «Обновить список».")
        return

    await query.message.chat.send_action(action=ChatAction.UPLOAD_VIDEO)
    with movie.path.open("rb") as movie_file:
        await query.message.reply_video(
            video=movie_file,
            filename=movie.filename,
            caption=f"Ваш файл: {movie.filename}",
            supports_streaming=True,
        )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message:
        await message.reply_text("Неизвестная команда. Используйте /movies.")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("Environment variable TELEGRAM_TOKEN is not set.")

    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("movies", movies_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    LOGGER.info("Movie bot is starting. Movies directory: %s", _movies_dir())
    application.run_polling()


if __name__ == "__main__":
    main()
