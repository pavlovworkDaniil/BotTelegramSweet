"""Telegram sweet shop bot.

This module implements a Telegram bot that acts as a small online store for
confectionery products.  The bot is intentionally lightweight and requires no
external database; all data about sweets is stored in memory.  This makes it a
good starting point for demonstration purposes and for local development.

To run the bot you will need to install the dependencies listed in
``requirements.txt`` and provide the bot token in the ``TELEGRAM_TOKEN``
environment variable before executing the script.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, MutableMapping

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler,
                          filters)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Sweet:
    """A single item that can be purchased in the shop."""

    id: str
    name: str
    price_rub: int
    description: str


SWEET_CATALOGUE: Dict[str, List[Sweet]] = {
    "chocolate": [
        Sweet(
            id="milk_chocolate",
            name="Молочный шоколад",
            price_rub=220,
            description="Классическая плитка молочного шоколада с легкой"
            " карамельной ноткой.",
        ),
        Sweet(
            id="dark_truffle",
            name="Трюфель 72%",
            price_rub=280,
            description="Темный шоколад с насыщенным вкусом какао и"
            " хрустящими какао-крупками.",
        ),
    ],
    "caramel": [
        Sweet(
            id="salted_caramel",
            name="Соленая карамель",
            price_rub=150,
            description="Нежная тянучка на сливках с легкой ноткой морской"
            " соли.",
        ),
        Sweet(
            id="hazelnut_caramel",
            name="Карамель с фундуком",
            price_rub=190,
            description="Мягкая карамель, украшенная дробленым фундуком.",
        ),
    ],
    "cookies": [
        Sweet(
            id="choco_chip_cookie",
            name="Печенье с шоколадной крошкой",
            price_rub=120,
            description="Домашнее печенье из сливочного теста, щедро"
            " посыпанное шоколадом.",
        ),
        Sweet(
            id="red_velvet_cookie",
            name="Печенье «Красный бархат»",
            price_rub=130,
            description="Мягкое печенье с нежным кремовым послевкусием.",
        ),
    ],
}


def _get_cart(user_data: MutableMapping[str, object]) -> Dict[str, int]:
    """Return the shopping cart stored in ``user_data``."""

    cart = user_data.setdefault("cart", {})
    if not isinstance(cart, dict):  # Defensive programming in case of misuse.
        user_data["cart"] = {}
        cart = user_data["cart"]
    return cart  # type: ignore[return-value]


def _format_currency(amount_rub: int) -> str:
    """Format an integer price in rubles using the ₽ symbol."""

    return f"{amount_rub} ₽"


def _build_categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=_category_title(category), callback_data=f"cat:{category}")]
        for category in SWEET_CATALOGUE
    ]
    buttons.append([InlineKeyboardButton(text="🛒 Корзина", callback_data="cart:view")])
    return InlineKeyboardMarkup(buttons)


def _build_sweets_keyboard(category: str) -> InlineKeyboardMarkup:
    sweets = SWEET_CATALOGUE.get(category)
    if not sweets:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu")]])

    buttons: List[List[InlineKeyboardButton]] = []
    for sweet in sweets:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{sweet.name} — {_format_currency(sweet.price_rub)}",
                    callback_data=f"item:{sweet.id}",
                )
            ]
        )

    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def _build_item_keyboard(sweet: Sweet) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Добавить в корзину", callback_data=f"add:{sweet.id}"),
            ],
            [
                InlineKeyboardButton("🛒 Открыть корзину", callback_data="cart:view"),
                InlineKeyboardButton("⬅️ Назад", callback_data="menu"),
            ],
        ]
    )


def _build_cart_keyboard(cart: Dict[str, int]) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    if cart:
        buttons.append(
            [
                InlineKeyboardButton("Очистить", callback_data="cart:clear"),
                InlineKeyboardButton("Оформить заказ", callback_data="cart:checkout"),
            ]
        )
    buttons.append([InlineKeyboardButton("⬅️ К товарам", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def _category_title(category: str) -> str:
    titles = {
        "chocolate": "Шоколад",
        "caramel": "Карамель",
        "cookies": "Печенье",
    }
    return titles.get(category, category)


def _find_sweet_by_id(sweet_id: str) -> Sweet | None:
    for sweets in SWEET_CATALOGUE.values():
        for sweet in sweets:
            if sweet.id == sweet_id:
                return sweet
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""

    user_first_name = update.effective_user.first_name if update.effective_user else "гость"
    text = (
        f"Привет, {user_first_name}! 👋\n"
        "Добро пожаловать в Sweet Shop — наш уютный магазин сладостей."
        "\n\nВыбирайте категорию, чтобы посмотреть ассортимент, или откройте"
        " корзину, чтобы оформить заказ."
    )
    message = update.effective_message
    if message:
        await message.reply_text(text, reply_markup=_build_categories_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide help information about the bot."""

    text = (
        "Я бот-магазин сладостей. Вот что я умею:\n"
        "• /menu — показать доступные категории сладостей.\n"
        "• /cart — показать вашу корзину.\n"
        "• /help — показать это сообщение.\n"
        "\nИспользуйте кнопки под сообщениями, чтобы добавлять товары в корзину и"
        " оформлять заказ."
    )
    message = update.effective_message
    if message:
        await message.reply_text(text)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /menu command."""

    message = update.effective_message
    if message:
        await message.reply_text("Выбирайте сладости:", reply_markup=_build_categories_keyboard())


async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /cart command."""

    cart = _get_cart(context.user_data)
    message = update.effective_message
    if message:
        await message.reply_text(_format_cart(cart), reply_markup=_build_cart_keyboard(cart))


def _format_cart(cart: Dict[str, int]) -> str:
    if not cart:
        return "Ваша корзина пока пуста. Загляните в меню и добавьте что-нибудь вкусное!"

    lines = ["🛒 Ваша корзина:"]
    total = 0
    for sweet_id, quantity in cart.items():
        sweet = _find_sweet_by_id(sweet_id)
        if not sweet:
            continue
        line_total = sweet.price_rub * quantity
        total += line_total
        lines.append(
            f"• {sweet.name} — {quantity} шт. × {_format_currency(sweet.price_rub)}"
            f" = {_format_currency(line_total)}"
        )

    lines.append("")
    lines.append(f"Итого к оплате: {_format_currency(total)}")
    lines.append(
        "Для завершения заказа нажмите «Оформить заказ» и наш менеджер свяжется"
        " с вами."
    )
    return "\n".join(lines)


async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses from the inline keyboards."""

    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()

    data = query.data or ""
    LOGGER.debug("Received callback data: %s", data)

    if data == "menu":
        await query.edit_message_text(
            text="Выбирайте сладости:",
            reply_markup=_build_categories_keyboard(),
        )
        return

    if data.startswith("cat:"):
        category = data.split(":", 1)[1]
        sweets = SWEET_CATALOGUE.get(category)
        if not sweets:
            await query.answer("Категория не найдена", show_alert=True)
            return

        await query.edit_message_text(
            text=f"Категория: {_category_title(category)}",
            reply_markup=_build_sweets_keyboard(category),
        )
        return

    if data.startswith("item:"):
        sweet_id = data.split(":", 1)[1]
        sweet = _find_sweet_by_id(sweet_id)
        if not sweet:
            await query.answer("Товар не найден", show_alert=True)
            return

        description = (
            f"<b>{sweet.name}</b>\n"
            f"Цена: {_format_currency(sweet.price_rub)}\n\n"
            f"{sweet.description}"
        )
        await query.edit_message_text(
            text=description,
            parse_mode=ParseMode.HTML,
            reply_markup=_build_item_keyboard(sweet),
        )
        return

    if data.startswith("add:"):
        sweet_id = data.split(":", 1)[1]
        sweet = _find_sweet_by_id(sweet_id)
        if not sweet:
            await query.answer("Товар не найден", show_alert=True)
            return

        cart = _get_cart(context.user_data)
        cart[sweet_id] = cart.get(sweet_id, 0) + 1
        await query.answer("Добавлено в корзину")
        await query.edit_message_reply_markup(reply_markup=_build_item_keyboard(sweet))
        return

    if data.startswith("cart:"):
        action = data.split(":", 1)[1]
        cart = _get_cart(context.user_data)

        if action == "view":
            await query.edit_message_text(
                text=_format_cart(cart),
                reply_markup=_build_cart_keyboard(cart),
            )
            return

        if action == "clear":
            cart.clear()
            await query.edit_message_text(
                text="Корзина очищена. Чем еще можем порадовать?",
                reply_markup=_build_cart_keyboard(cart),
            )
            return

        if action == "checkout":
            if not cart:
                await query.answer("Корзина пуста", show_alert=True)
                return

            await query.edit_message_text(
                text=(
                    "Спасибо за заказ! 🎉\n"
                    "Наш менеджер свяжется с вами в ближайшее время для"
                    " уточнения деталей доставки и оплаты."
                ),
                reply_markup=_build_categories_keyboard(),
            )
            cart.clear()
            return

    await query.answer("Неизвестная команда", show_alert=True)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unrecognised commands."""

    message = update.effective_message
    if message:
        await message.reply_text(
            "Я пока не знаю такой команды. Используйте /menu, чтобы выбрать сладости."
        )


def main() -> None:
    """Entrypoint for the bot application."""

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError(
            "Environment variable TELEGRAM_TOKEN is not set. "
            "Export the bot token before starting the bot."
        )

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("cart", cart_command))
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    LOGGER.info("Sweet Shop bot is starting")
    application.run_polling()


if __name__ == "__main__":
    main()

