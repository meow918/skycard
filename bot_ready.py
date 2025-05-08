import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

data_file = "data.json"
users = {}
if os.path.exists(data_file):
    with open(data_file, "r") as f:
        users = json.load(f)

pending_requests = {}
banks = ["Сбербанк", "Тинькофф", "Альфа-Банк", "ВТБ", "Райффайзен", "Газпромбанк"]

def save_data():
    with open(data_file, "w") as f:
        json.dump(users, f)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 Добавить карту")],
        [KeyboardButton(text="📈 Статистика"), KeyboardButton(text="📂 Архив")],
        [KeyboardButton(text="⚔️ Уровень Sky")]
    ],
    resize_keyboard=True
)

# === Роутеры ===

@dp.message(lambda m: m.text == "/start")
async def start(message: types.Message):
    uid = str(message.from_user.id)
    if uid not in users:
        users[uid] = {"cards": [], "incoming": 0, "xp": 0, "rate": 0.015, "history": []}
        save_data()
    await message.answer("Добро пожаловать в Sky Card", reply_markup=main_menu)

@dp.message(lambda m: m.text == "💳 Добавить карту")
async def add_card(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b, callback_data=f"bank_{b}")] for b in banks])
    await message.answer("Выберите банк:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("bank_"))
async def select_bank(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    bank = callback.data.split("bank_")[1]
    users[uid]["pending_card"] = {"bank": bank}
    save_data()
    await callback.message.answer("Введите срок аренды в часах:")
    await callback.answer()

@dp.message(lambda m: 'pending_card' in users.get(str(m.from_user.id), {}))
async def card_details(message: types.Message):
    uid = str(message.from_user.id)
    card = users[uid]["pending_card"]
    try:
        if 'duration_hours' not in card:
            card['duration_hours'] = int(message.text)
            await message.answer("Введите лимит карты:")
        elif 'limit' not in card:
            card['limit'] = int(message.text)
            card['status'] = 'на модерации'
            users[uid]["cards"].append(card)
            del users[uid]["pending_card"]
            save_data()
            idx = len(users[uid]["cards"]) - 1
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_card_{uid}_{idx}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_card_{uid}_{idx}")
            ]])
            await bot.send_message(ADMIN_ID, f"Карта от {uid}: {card['bank']}, {card['limit']}₽", reply_markup=kb)
            await message.answer("Карта отправлена на модерацию.")
    except:
        await message.answer("Введите число.")

@dp.callback_query(lambda c: c.data.startswith("approve_card_"))
async def approve_card(callback: types.CallbackQuery):
    _, _, uid, idx = callback.data.split("_")
    users[uid]["cards"][int(idx)]["status"] = "активна"
    save_data()
    await bot.send_message(uid, "Карта активирована.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("reject_card_"))
async def reject_card(callback: types.CallbackQuery):
    _, _, uid, idx = callback.data.split("_")
    users[uid]["cards"].pop(int(idx))
    save_data()
    await bot.send_message(uid, "Карта отклонена.")
    await callback.answer()

@dp.message(lambda m: m.text == "📂 Архив")
async def show_cards(message: types.Message):
    uid = str(message.from_user.id)
    cards = users[uid].get("cards", [])
    if not cards:
        return await message.answer("Нет карт.")
    for i, c in enumerate(cards):
        await message.answer(f"{i+1}. {c['bank']}\nСтатус: {c['status']}\nСрок: {c['duration_hours']} ч\nЛимит: {c['limit']}₽")

@dp.message(lambda m: m.text == "📈 Статистика")
async def stats(message: types.Message):
    uid = str(message.from_user.id)
    u = users[uid]
    profit = u['incoming'] * u['rate']
    await message.answer(f"Оборот: {u['incoming']}₽\nДоход: {profit:.2f}₽\nXP: {u['xp']}")

@dp.message(lambda m: m.text == "⚔️ Уровень Sky")
async def level(message: types.Message):
    xp = users[str(message.from_user.id)]["xp"]
    await message.answer(f"Ваш XP: {xp} | Уровни в разработке")

# === Webhook ===

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

@app.post("/webhook")
async def process_webhook(request: Request):
    update = types.Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}