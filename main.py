import asyncio

import os

import time

import random

import shutil

import logging

from datetime import datetime

import aiosqlite

from groq import AsyncGroq

from aiogram import Bot, Dispatcher, F

from aiogram.types import (

    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,

    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

)

from aiogram.filters import CommandStart, Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

 

# --- ВСТАВЬ СВОИ ДАННЫЕ СЮДА ---

BOT_TOKEN = "9297074957:AAHgXbP98qptiyJhUQE9Su3rn7yiqUoXb98"

ADMIN_ID = 6921885296  # <-- ВПИШИ СЮДА ВСЕ ЦИФРЫ СВОЕГО ID ИЗ @userinfobot

GROQ_API_KEY = "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"

 

# Постоянное хранилище Bothost (/app/data), чтобы база не пропадала при обновлениях

DATA_DIR = os.getenv("DATA_DIR", "/app/data")

if not os.path.exists(DATA_DIR):

    try:

        os.makedirs(DATA_DIR, exist_ok=True)

    except Exception:

        DATA_DIR = "."

DB_NAME = os.path.join(DATA_DIR, "momo_database.db")

 

# --- КАРТИНКИ МОМО (file_id) ---

PHOTO_ANGRY = "AgACAgIAAxkBAAKhBmsDmSnWaGVkGdUe9mjAIa52FH89AAINHWsbVAEgSNRj-CUMv7u5AQADAgADeQADPQQ"

PHOTO_SHY = "AgACAgIAAxkBAAKgyWsDlBJhJZadRThIyR-G1GsrVGtxAAIKHWsbVAEgSMKrd1cCVVXkAQADAgADeQADPQQ"

PHOTO_LOVE = "AgACAgIAAxkBAAKgy2sDlBkS44k46CTYNhZITcHje09gAAILHWsbVAEgSLzZ6nmSWbItAQADAgADeQADPQQ"

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY and "ВСТАВЬ" not in GROQ_API_KEY else None

 

ai_cooldown = {}

chat_xp_cooldown = {}

 

MOMO_TIPS = [

    "Болтай со мной в ЛС или позови по имени в чате — за живое общение капает опыт симпатии!",

    "Каждые 10 уровней комиссия на вывод падает, а на 86+ уровне она становится 0%!",

    "Не забывай нажимать «☀️ Поздороваться» раз в сутки, иначе я решу, что ты про меня забыл, бака!",

    "Каждые 3 часа меня можно погладить — только не вздумай растрепать мне волосы!",

    "За каждого приглашенного друга ты получишь +30 BAKA и сразу +25 XP к нашим отношениям.",

    "Добавь меня в общий чат с друзьями — я буду отвечать всем, кто напишет «Момо»!",

    "На каждом новом уровне симпатии открывается уникальная фича в твоем профиле!",

    "Вывод звезд доступен прямо с 1 уровня, как только накопишь 1000 BAKA (50 ⭐)."

]

 

# Уникальные фичи для каждого из 100 уровней

LEVEL_FEATURES = {

    1: "Право находиться в одном чате с Момо",

    5: "Момо запомнила твой ник (почти)",

    10: "Снижение комиссии до 9% + статус «Терпимый»",

    15: "Разрешение здороваться первым",

    20: "Снижение комиссии до 8% + иммунитет к ворчанию",

    25: "Момо тайно проверяет твой профиль раз в день",

    30: "Снижение комиссии до 7% + доступ к мягким ответам",

    40: "Снижение комиссии до 6% + статус «Почти друг»",

    50: "Снижение комиссии до 5% + личный дегустатор бенто 🍱",

    60: "Снижение комиссии до 4% + Момо краснеет при встрече",

    70: "Снижение комиссии до 3% + статус «Особенный бака»",

    80: "Снижение комиссии до 2% + право на комплименты",

    86: "Комиссия на вывод 0% навсегда! 💎",

    95: "Момо почти готова признаться в чувствах...",

    100: "Абсолютный максимум: Сердце Цундере Момо 💖"

}

 

def get_level_feature(lvl: int) -> str:

    if lvl in LEVEL_FEATURES:

        return LEVEL_FEATURES[lvl]

    verbs = ["Тайный взгляд", "Скрытая симпатия", "Мягкий тон", "Теплая улыбка", "Доверие Момо", "Особый знак", "Забота цундере", "Ночной чат", "Личный секрет", "Искры в глазах"]

    return f"{verbs[lvl % 10]} (Ступень #{lvl})"

 

class BotStates(StatesGroup):

    waiting_promo = State()

    waiting_withdraw = State()

    admin_broadcast = State()

    admin_new_promo = State()

    admin_set_sub = State()

async def init_db():

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("PRAGMA journal_mode=WAL;")

        await db.execute("PRAGMA synchronous=FULL;")

        await db.execute(f"""

            CREATE TABLE IF NOT EXISTS users (

                user_id INTEGER PRIMARY KEY,

                username TEXT,

                first_name TEXT,

                balance INTEGER DEFAULT 0,

                affection_lvl INTEGER DEFAULT 1,

                affection_xp INTEGER DEFAULT 0,

                referrer_id INTEGER,

                referrals_count INTEGER DEFAULT 0,

                last_daily INTEGER DEFAULT 0,

                last_pet INTEGER DEFAULT 0,

                joined_at INTEGER DEFAULT {now_ts}

            )

        """)

        for col, definition in [

            ("affection_lvl", "INTEGER DEFAULT 1"),

            ("affection_xp", "INTEGER DEFAULT 0"),

            ("joined_at", f"INTEGER DEFAULT {now_ts}")

        ]:

            try:

                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

            except Exception:

                pass

        await db.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT, members_count INTEGER DEFAULT 0)")

        await db.execute("CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")

        await db.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, code TEXT)")

        await db.execute("CREATE TABLE IF NOT EXISTS settings (key PRIMARY KEY, value TEXT)")

        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_enabled', '0')")

        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_channel', '')")

        await db.commit()

 

async def get_setting(key: str):

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:

            row = await cursor.fetchone()

            return row if row else None

 

async def set_setting(key: str, value: str):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

        await db.commit()

 

async def ensure_user(user):

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,)) as cur:

            if not await cur.fetchone():

                await db.execute(

                    "INSERT INTO users (user_id, username, first_name, balance, affection_lvl, affection_xp, joined_at) VALUES (?, ?, ?, 0, 1, 0, ?)",

                    (user.id, user.username or "", user.first_name or "Бака", now_ts)

                )

                await db.commit()

 

def xp_needed_for_level(lvl: int) -> int:

    return 50 + (lvl * 10)

 

async def add_affection_xp(user_id: int, xp_amount: int) -> tuple[int, int, bool]:

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT affection_lvl, affection_xp FROM users WHERE user_id = ?", (user_id,)) as cur:

            row = await cur.fetchone()

            lvl, xp = row if row else (1, 0)

        if lvl >= 100:

            return 100, 0, False

        xp += xp_amount

        leveled_up = False

        while lvl < 100 and xp >= xp_needed_for_level(lvl):

            xp -= xp_needed_for_level(lvl)

            lvl += 1

            leveled_up = True

        if lvl == 100:

            xp = 0

        await db.execute("UPDATE users SET affection_lvl = ?, affection_xp = ? WHERE user_id = ?", (lvl, xp, user_id))

        await db.commit()

        return lvl, xp, leveled_up

 

def get_rank_and_fee(lvl: int) -> tuple[str, float, str]:

    if lvl < 10:

        return "Враг №1 💢", 0.10, PHOTO_ANGRY

    elif lvl < 20:

        return "Терпимый бака 😒", 0.09, PHOTO_ANGRY

    elif lvl < 30:

        return "Знакомый 😐", 0.08, PHOTO_ANGRY

    elif lvl < 40:

        return "Собеседник 🙂", 0.07, PHOTO_ANGRY

    elif lvl < 50:

        return "Почти друг 😳", 0.06, PHOTO_SHY

    elif lvl < 60:

        return "Близкий друг 😊", 0.05, PHOTO_SHY

    elif lvl < 70:

        return "Тайный краш 💕", 0.04, PHOTO_SHY

    elif lvl < 80:

        return "Особый человек 💓", 0.03, PHOTO_SHY

    elif lvl < 86:

        return "Почти любимый 💗", 0.02, PHOTO_SHY

    else:

        return "Любимчик Момо 💖", 0.00, PHOTO_LOVE

 

def make_hearts_bar(current: int, target: int, length: int = 6) -> str:

    if target <= 0:

        return "❤️" * length

    filled = int(round(length * min(max(current / target, 0.0), 1.0)))

    return "❤️" * filled + "🖤" * (length - filled)

 

def main_menu():

    buttons = [

        [KeyboardButton(text="🎀 Профиль и Стата"), KeyboardButton(text="🎁 Промокод")],

        [KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="⭐ Вывод звезд")],

        [KeyboardButton(text="🏆 Топ игроков")]

    ]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

 

def profile_inline_kb():

    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="☀️ Поздороваться", callback_data="act_daily"),

         InlineKeyboardButton(text="✨ Погладить", callback_data="act_pet")],

        [InlineKeyboardButton(text="🔄 Обновить стату", callback_data="act_refresh"),

         InlineKeyboardButton(text="⭐ Вывести", callback_data="act_withdraw")]

    ])

 

def admin_menu():

    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="📊 Пульс проекта (Статистика)", callback_data="adm_stats")],

        [InlineKeyboardButton(text="📢 Рассылка (ЛС + Чаты)", callback_data="adm_broadcast")],

        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="adm_promo")],

        [InlineKeyboardButton(text="🔒 Обязательная подписка", callback_data="adm_sub")],

        [InlineKeyboardButton(text="💾 Скачать базу (Бэкап)", callback_data="adm_backup")]

    ])

 

# --- АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ БАЗЫ ПРИ ОТПРАВКЕ ФАЙЛА .DB АДМИНОМ ---

@dp.message(F.document)

async def auto_restore_db(message: Message):

    if message.from_user.id != ADMIN_ID or message.chat.type != "private":

        return

    if not message.document.file_name or not message.document.file_name.endswith(".db"):

        return

    try:

        if os.path.exists(DB_NAME):

            shutil.copy2(DB_NAME, DB_NAME + ".bak")

        file = await bot.get_file(message.document.file_id)

        await bot.download_file(file.file_path, DB_NAME)

        await init_db()

        async with aiosqlite.connect(DB_NAME) as db:

            u_cnt = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())

            t_baka = (await (await db.execute("SELECT SUM(balance) FROM users")).fetchone()) or 0

        await message.reply(

            f"✅ <b>База данных мгновенно восстановлена!</b>\n"

            f"👤 Игроков в базе: <b>{u_cnt}</b>\n"

            f"💰 Общий баланс: <code>{t_baka} BAKA</code>",

            parse_mode="HTML"

        )

    except Exception as e:

        if os.path.exists(DB_NAME + ".bak"):

            shutil.copy2(DB_NAME + ".bak", DB_NAME)

        await message.reply(f"❌ Ошибка восстановления (откатила старую базу): <code>{e}</code>", parse_mode="HTML")

 

@dp.message(F.photo)

async def get_photo_id(message: Message):

    if message.from_user.id == ADMIN_ID and message.chat.type == "private":

        await message.reply(f"🖼 <b>Код картинки:</b>\n<code>{message.photo[-1].file_id}</code>", parse_mode="HTML")

@dp.my_chat_member()

async def on_chat_member(event):

    if event.chat.type in ["group", "supergroup"]:

        if event.new_chat_member.status in ["member", "administrator"]:

            try:

                cnt = await bot.get_chat_member_count(event.chat.id)

            except Exception:

                cnt = 0

            async with aiosqlite.connect(DB_NAME) as db:

                await db.execute("REPLACE INTO chats (chat_id, title, members_count) VALUES (?, ?, ?)", (event.chat.id, event.chat.title, cnt))

                await db.commit()

            if ADMIN_ID:

                await bot.send_message(ADMIN_ID, f"🔔 <b>Новый чат!</b>\n📌 <b>{event.chat.title}</b> ({cnt} чел.)", parse_mode="HTML")

        elif event.new_chat_member.status in ["left", "kicked"]:

            async with aiosqlite.connect(DB_NAME) as db:

                await db.execute("DELETE FROM chats WHERE chat_id = ?", (event.chat.id,))

                await db.commit()

 

@dp.message(CommandStart())

async def cmd_start(message: Message):

    if message.chat.type != "private":

        return

    user = message.from_user

    args = message.text.split()

    ref_id = int(args) if len(args) > 1 and args.isdigit() and int(args) != user.id else None

    now_ts = int(time.time())

 

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,)) as cursor:

            exists = await cursor.fetchone()

        if not exists:

            await db.execute(

                "INSERT INTO users (user_id, username, first_name, balance, affection_lvl, affection_xp, referrer_id, joined_at) VALUES (?, ?, ?, 0, 1, 0, ?, ?)",

                (user.id, user.username or "", user.first_name or "Бака", ref_id, now_ts)

            )

            await db.commit()

            if ref_id:

                async with aiosqlite.connect(DB_NAME) as db2:

                    await db2.execute("UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1 WHERE user_id = ?", (ref_id,))

                    await db2.commit()

                await add_affection_xp(ref_id, 25)

                try:

                    await bot.send_message(ref_id, f"Х-хм! Новый реферал: <b>+30 BAKA</b> и <b>+25 XP</b> к симпатии!", parse_mode="HTML")

                except Exception:

                    pass

 

    welcome_text = (

        "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\n"

        "Я — <b>Цундере Момо</b>.\n\n"

        "<blockquote>💬 Болтай со мной в чате (я ИИ!)\n"

        "💕 Качай 100 уровней симпатии (на каждом уровне — своя фича!)\n"

        "⭐ Выводи звезды с 1 уровня от 1000 BAKA (50 ⭐)</blockquote>"

    )

    if PHOTO_ANGRY:

        await message.answer_photo(PHOTO_ANGRY, caption=welcome_text, reply_markup=main_menu(), parse_mode="HTML")

    else:

        await message.answer(welcome_text, reply_markup=main_menu(), parse_mode="HTML")

 

async def build_profile_card(user_id: int) -> tuple[str, str]:

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT balance, affection_lvl, affection_xp, referrals_count, joined_at FROM users WHERE user_id = ?", (user_id,)) as cur:

            row = await cur.fetchone()

            bal, lvl, xp, refs, joined_at = row if row else (0, 1, 0, 0, now_ts)

        async with db.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (bal,)) as cur:

            rank_pos = (await cur.fetchone()) + 1

        async with db.execute("SELECT COUNT(*) FROM users") as cur:

            total_users = (await cur.fetchone())

 

    if not joined_at:

        joined_at = now_ts

    days_known = max(1, (now_ts - joined_at) // 86400 + 1)

    date_str = datetime.fromtimestamp(joined_at).strftime("%d.%m.%Y")

 

    stars = round(bal / 20, 2)

    rank_name, fee, photo_id = get_rank_and_fee(lvl)

    req_xp = xp_needed_for_level(lvl) if lvl < 100 else 0

    hearts = make_hearts_bar(xp, req_xp) if lvl < 100 else "❤️❤️❤️❤️❤️❤️"

    xp_line = f"{hearts} ({xp}/{req_xp} XP)" if lvl < 100 else f"{hearts} (MAX)"

    lvl_perk = get_level_feature(lvl)

    tip = random.choice(MOMO_TIPS)

 

    text = (

        f"📊 <b>СТАТИСТИКА ИГРОКА</b>\n"

        f"<blockquote>"

        f"💰 Баланс: <code>{bal} BAKA</code> │ ⭐ <code>{stars}</code>\n"

        f"💕 Симпатия: <code>{lvl}/100 ур.</code> │ 🎖 Ранг: <b>{rank_name}</b>\n"

        f"👥 Друзей: <code>{refs}</code> │ 💸 Комиссия: <code>{int(fee*100)}%</code>\n"

        f"🏆 Место в топе: <code>#{rank_pos} из {total_users}</code>"

        f"</blockquote>\n\n"

        f"✨ <b>Фича {lvl} уровня:</b> <i>{lvl_perk}</i>\n"

        f"💓 <b>До {min(100, lvl + 1)} ур.:</b> {xp_line}\n\n"

        f"📅 <b>Первое знакомство:</b> {days_known} дн. вместе (с {date_str})\n"

        f"💡 <i>Подсказка: {tip}</i>"

    )

    return text, photo_id

 

@dp.message(F.text == "🎀 Профиль и Стата")

async def profile_msg(message: Message):

    await ensure_user(message.from_user)

    text, photo_id = await build_profile_card(message.from_user.id)

    if photo_id:

        await message.answer_photo(photo_id, caption=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

    else:

        await message.answer(text, reply_markup=profile_inline_kb(), parse_mode="HTML")

 

@dp.callback_query(F.data == "act_refresh")

async def cb_refresh(call: CallbackQuery):

    text, _ = await build_profile_card(call.from_user.id)

    try:

        if call.message.photo:

            await call.message.edit_caption(caption=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

        else:

            await call.message.edit_text(text=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

    except Exception:

        pass

    await call.answer("Обновлено!")

 

@dp.callback_query(F.data == "act_daily")

async def cb_daily(call: CallbackQuery):

    user_id = call.from_user.id

    await ensure_user(call.from_user)

    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last_daily = (await (await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))).fetchone())

        if now - last_daily < 86400:

            await call.answer(f"Уже здоровались! Жди {round((86400 - (now - last_daily))/3600, 1)} ч. 💢", show_alert=True)

            return

        bonus = random.randint(5, 15)

        await db.execute("UPDATE users SET last_daily = ?, balance = balance + ? WHERE user_id = ?", (now, bonus, user_id))

        await db.commit()

    lvl, _, up = await add_affection_xp(user_id, 15)

    await call.answer(f"+{bonus} BAKA и +15 XP!" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_refresh(call)

 

@dp.callback_query(F.data == "act_pet")

async def cb_pet(call: CallbackQuery):

    user_id = call.from_user.id

    await ensure_user(call.from_user)

    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last_pet = (await (await db.execute("SELECT last_pet FROM users WHERE user_id = ?", (user_id,))).fetchone())

        if now - last_pet < 10800:

            await call.answer(f"Убери руки! Жди {int((10800 - (now - last_pet))/60)} мин. 😳", show_alert=True)

            return

        await db.execute("UPDATE users SET last_pet = ? WHERE user_id = ?", (now, user_id))

        await db.commit()

    lvl, _, up = await add_affection_xp(user_id, 10)

    await call.answer("Н-не трогай меня, бака! (+10 XP)" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_refresh(call)

 

@dp.callback_query(F.data == "act_withdraw")

async def cb_withdraw(call: CallbackQuery, state: FSMContext):

    await call.answer()

    await withdraw_logic(call.from_user.id, call.message, state)

 

@dp.message(F.text == "🏆 Топ игроков")

async def top_players(message: Message):

    async with aiosqlite.connect(DB_NAME) as db:

        top_bal = await (await db.execute("SELECT first_name, balance, affection_lvl FROM users ORDER BY balance DESC LIMIT 10")).fetchall()

    medals = ["🥇", "🥈", "🥉"]

    lines = [f"{medals[i] if i < 3 else str(i+1)+'.'} <b>{(n or 'Бака').replace('<','')}</b> — <code>{b} BAKA</code> (💕 {l} ур.)" for i, (n, b, l) in enumerate(top_bal)]

    await message.answer(f"🏆 <b>Топ-10 богачей Момо:</b>\n\n<blockquote>{chr(10).join(lines) or 'Пусто'}</blockquote>", parse_mode="HTML")

 

@dp.message(F.text == "💌 Позвать друзей")

async def referrals(message: Message):

    bot_info = await bot.get_me()

    await message.answer(

        f"Зови друзей, бака! 🌸\n<blockquote>∙ <b>+30 BAKA</b> и <b>+25 XP</b> за каждого</blockquote>\n\n"

        f"🔗 Ссылка:\n<code>https://t.me{bot_info.username}?start={message.from_user.id}</code>",

        parse_mode="HTML"

    )

 

@dp.message(F.text == "🎁 Промокод")

async def promo_start(message: Message, state: FSMContext):

    await message.answer("Вводи промокод:")

    await state.set_state(BotStates.waiting_promo)

 

@dp.message(BotStates.waiting_promo)

async def promo_process(message: Message, state: FSMContext):

    code = message.text.strip()

    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        if await (await db.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (user_id, code))).fetchone():

            await message.answer("Ты уже вводил этот код! 💢")

            await state.clear()

            return

        promo = await (await db.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (code,))).fetchone()

        if not promo or promo <= 0:

            await message.answer("Неверный код или закончились активации!")

        else:

            await db.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))

            await db.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code))

            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo, user_id))

            await db.commit()

            await message.answer(f"Начислила <b>{promo} BAKA</b>! 🌸", parse_mode="HTML")

    await state.clear()

 

async def check_subscription(user_id: int) -> tuple[bool, str]:

    if await get_setting("sub_enabled") != "1":

        return True, ""

    channel = await get_setting("sub_channel")

    if not channel:

        return True, ""

    try:

        m = await bot.get_chat_member(chat_id=channel, user_id=user_id)

        return (m.status in ["member", "administrator", "creator"]), channel

    except Exception:

        return True, ""

 

async def withdraw_logic(user_id: int, message: Message, state: FSMContext):

    is_sub, channel = await check_subscription(user_id)

    if not is_sub:

        await message.answer(

            f"Сначала подпишись на {channel}! 💢",

            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub_again")]])

        )

        return

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (user_id,))).fetchone()

        bal, lvl = row if row else (0, 1)

    if bal < 1000:

        await message.answer(f"У тебя <b>{bal} BAKA</b>. Вывод доступен с 1 уровня от <b>1000 BAKA</b> (50 ⭐)!", parse_mode="HTML")

        return

    _, fee, _ = get_rank_and_fee(lvl)

    await message.answer(

        f"⭐ <b>Вывод звезд (доступен с 1 ур.)</b>\n"

        f"Баланс: <b>{bal} BAKA</b> | Твоя комиссия ({lvl} ур.): <b>{int(fee*100)}%</b>\n"

        f"Введи сумму BAKA для обмена (минимум 1000):",

        parse_mode="HTML"

    )

    await state.set_state(BotStates.waiting_withdraw)

 

@dp.message(F.text == "⭐ Вывод звезд")

async def withdraw_start(message: Message, state: FSMContext):

    await ensure_user(message.from_user)

    await withdraw_logic(message.from_user.id, message, state)

 

@dp.callback_query(F.data == "check_sub_again")

async def recheck_sub(call: CallbackQuery, state: FSMContext):

    is_sub, _ = await check_subscription(call.from_user.id)

    if is_sub:

        await call.message.delete()

        await withdraw_logic(call.from_user.id, call.message, state)

    else:

        await call.answer("Ты не подписался!", show_alert=True)

 

@dp.message(BotStates.waiting_withdraw)

async def withdraw_process(message: Message, state: FSMContext):

    if not message.text.isdigit() or int(message.text) < 1000:

        await message.answer("Введи число от 1000!")

        return

    amount = int(message.text)

    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        bal, lvl = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (user_id,))).fetchone()

        if amount > bal:

            await message.answer("Не хватает BAKA!")

            await state.clear()

            return

        _, fee, _ = get_rank_and_fee(lvl)

        final_stars = round((amount / 20) * (1 - fee), 2)

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

        await db.commit()

    await message.answer(f"✅ Заявка принята! К выплате: <b>{final_stars} ⭐</b>", parse_mode="HTML")

    if ADMIN_ID:

        await bot.send_message(ADMIN_ID, f"💸 Вывод: @{message.from_user.username} (<code>{user_id}</code>) ➡️ <b>{final_stars} ⭐</b>", parse_mode="HTML")

    await state.clear()

 

# --- СКРЫТАЯ АДМИНКА (/admin) ---

@dp.message(Command("admin"))

async def open_admin(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(f"⛔ Нет доступа. Твой ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

        return

    await message.answer("👑 <b>Админ-панель Момо:</b>\n<i>(Чтобы восстановить базу — просто отправь сюда файл .db)</i>", reply_markup=admin_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")

async def adm_stats(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID:

        return

    async with aiosqlite.connect(DB_NAME) as db:

        u_cnt = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())

        c_cnt = (await (await db.execute("SELECT COUNT(*) FROM chats")).fetchone())

        t_baka = (await (await db.execute("SELECT SUM(balance) FROM users")).fetchone()) or 0

        chats = await (await db.execute("SELECT title, members_count FROM chats ORDER BY members_count DESC LIMIT 10")).fetchall()

    c_list = "\n".join([f"∙ <b>{c}</b> ({c} чел.)" for c in chats]) or "Нет чатов"

    await call.message.answer(f"📊 ЛС: <b>{u_cnt}</b> | Чатов: <b>{c_cnt}</b>\n💰 В банке: <code>{t_baka} BAKA</code>\n\n{c_list}", parse_mode="HTML")

    await call.answer()

 

@dp.callback_query(F.data == "adm_backup")

async def adm_backup(call: CallbackQuery):

    if call.from_user.id == ADMIN_ID and os.path.exists(DB_NAME):

        await call.message.answer_document(FSInputFile(DB_NAME), caption="💾 Бэкап базы (просто отправь этот файл боту для восстановления)")

    await call.answer()

 

@dp.callback_query(F.data == "adm_promo")

async def adm_promo(call: CallbackQuery, state: FSMContext):

    if call.from_user.id == ADMIN_ID:

        await call.message.answer("Формат: <code>КОД НАГРАДА КОЛ_ВО</code>", parse_mode="HTML")

        await state.set_state(BotStates.admin_new_promo)

    await call.answer()

 

@dp.message(BotStates.admin_new_promo)

async def adm_promo_save(message: Message, state: FSMContext):

    try:

        c, r, u = message.text.split()

        async with aiosqlite.connect(DB_NAME) as db:

            await db.execute("REPLACE INTO promos VALUES (?, ?, ?)", (c, int(r), int(u)))

            await db.commit()

        await message.answer(f"✅ Код <code>{c}</code> создан!", parse_mode="HTML")

    except Exception:

        await message.answer("❌ Ошибка формата")

    await state.clear()

 

@dp.callback_query(F.data == "adm_sub")

async def adm_sub(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID:

        return

    st = "ВКЛ ✅" if await get_setting("sub_enabled") == "1" else "ВЫКЛ ❌"

    ch = await get_setting("sub_channel") or "Не задан"

    kb = InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data="toggle_sub")],

        [InlineKeyboardButton(text="✏️ Канал", callback_data="edit_sub_channel")]

    ])

    await call.message.answer(f"🔒 ОП: {st}\nКанал: <code>{ch}</code>", reply_markup=kb, parse_mode="HTML")

    await call.answer()

 

@dp.callback_query(F.data == "toggle_sub")

async def toggle_sub(call: CallbackQuery):

    await set_setting("sub_enabled", "0" if await get_setting("sub_enabled") == "1" else "1")

    await adm_sub(call)

 

@dp.callback_query(F.data == "edit_sub_channel")

async def edit_sub_channel(call: CallbackQuery, state: FSMContext):

    await call.message.answer("Введи @канал или ID:")

    await state.set_state(BotStates.admin_set_sub)

    await call.answer()

 

@dp.message(BotStates.admin_set_sub)

async def save_sub_channel(message: Message, state: FSMContext):

    await set_setting("sub_channel", message.text.strip())

    await message.answer("✅ Сохранено!")

    await state.clear()

 

@dp.callback_query(F.data == "adm_broadcast")

async def adm_broadcast(call: CallbackQuery, state: FSMContext):

    if call.from_user.id == ADMIN_ID:

        await call.message.answer("Отправь пост для рассылки:")

        await state.set_state(BotStates.admin_broadcast)

    await call.answer()

 

@dp.message(BotStates.admin_broadcast)

async def adm_broadcast_send(message: Message, state: FSMContext):

    await state.clear()

    async with aiosqlite.connect(DB_NAME) as db:

        targets = set([r for r in await (await db.execute("SELECT user_id FROM users")).fetchall()] +

                      [r for r in await (await db.execute("SELECT chat_id FROM chats")).fetchall()])

    sent = 0

    for cid in targets:

        try:

            await message.copy_to(cid)

            sent += 1

            await asyncio.sleep(0.05)

        except Exception:

            pass

    await message.answer(f"✅ Доставлено: <b>{sent}</b>", parse_mode="HTML")

 

# --- ЖИВОЙ ИИ ДИАЛОГ ---

@dp.message(F.text)

async def ai_chat_handler(message: Message):

    if not message.text or message.text.startswith("/"):

        return

    if not groq_client:

        if message.chat.type == "private":

            await message.answer("⚠️ Ключ GROQ_API_KEY не вставлен в main.py!")

        return

 

    is_private = message.chat.type == "private"

    bot_me = await bot.get_me()

    is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot_me.id

    is_mention = "момо" in message.text.lower() or f"@{bot_me.username.lower()}" in message.text.lower()

 

    if not is_private and not is_mention and not is_reply:

        return

 

    user_id = message.from_user.id

    now = time.time()

    if now - ai_cooldown.get(user_id, 0) < 3:

        return

    ai_cooldown[user_id] = now

 

    await ensure_user(message.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT affection_lvl FROM users WHERE user_id = ?", (user_id,))).fetchone()

        lvl = row if row else 1

 

    if now - chat_xp_cooldown.get(user_id, 0) > 180 and lvl < 100:

        chat_xp_cooldown[user_id] = now

        lvl, _, _ = await add_affection_xp(user_id, 5)

 

    mood = "грубая ворчливая цундере" if lvl <= 30 else ("смущающаяся цундере" if lvl <= 80 else "влюбленная застенчивая цундере")

    prompt = f"Ты Цундере Момо, аниме-девушка. Симпатия к игроку: {lvl}/100 ур. ({mood}). Отвечай по-русски, коротко (1-2 предложения), эмоционально."

 

    try:

        await bot.send_chat_action(message.chat.id, "typing")

        comp = await groq_client.chat.completions.create(

            model="llama-3.1-8b-instant",

            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": message.text[:500]}],

            max_tokens=180

        )

        await message.reply(comp.choices.message.content)

    except Exception as e:

        logging.error(f"Groq error: {e}")

        if is_private and user_id == ADMIN_ID:

            await message.answer(f"⚠️ Ошибка ИИ Groq: <code>{e}</code>", parse_mode="HTML")

 

async def main():

    await init_db()

    await dp.start_polling(bot)

 

if __name__ == "__main__":

    asyncio.run(main())
