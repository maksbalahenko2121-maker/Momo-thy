import asyncio

import os

import time

import random

import logging

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

DB_NAME = "momo_database.db"

 

# --- КАРТИНКИ МОМО (file_id) ---

PHOTO_ANGRY = "AgACAgIAAxkBAAKgy2sDlBkS44k46CTYNhZITcHje09gAAILHWsbVAEgSLzZ6nmSWbItAQADAgADeQADPQQ"

PHOTO_SHY = "AgACAgIAAxkBAAKgyWsDlBJhJZadRThIyR-G1GsrVGtxAAIKHWsbVAEgSMKrd1cCVVXkAQADAgADeQADPQQ"

PHOTO_LOVE = "AgACAgIAAxkBAAKgyWsDlBJhJZadRThIyR-G1GsrVGtxAAIKHWsbVAEgSMKrd1cCVVXkAQADAgADeQADPQQ"

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY and "ВСТАВЬ" not in GROQ_API_KEY else None

 

ai_cooldown = {}

chat_xp_cooldown = {}

 

class BotStates(StatesGroup):

    waiting_promo = State()

    waiting_withdraw = State()

    admin_broadcast = State()

    admin_new_promo = State()

    admin_set_sub = State()

    admin_upload_db = State()

 

async def init_db():

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("""

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

                last_pet INTEGER DEFAULT 0

            )

        """)

        for col, definition in [("affection_lvl", "INTEGER DEFAULT 1"), ("affection_xp", "INTEGER DEFAULT 0")]:

            try:

                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

            except Exception:

                pass

        await db.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT, members_count INTEGER DEFAULT 0)")

        await db.execute("CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")

        await db.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, code TEXT)")

        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_enabled', '0')")

        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_channel', '')")

        await db.commit()

 

async def get_setting(key: str):

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:

            row = await cursor.fetchone()

            return row[0] if row else None

 

async def set_setting(key: str, value: str):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

        await db.commit()

 

async def ensure_user(user):

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,)) as cur:

            if not await cur.fetchone():

                await db.execute(

                    "INSERT INTO users (user_id, username, first_name, balance, affection_lvl, affection_xp) VALUES (?, ?, ?, 0, 1, 0)",

                    (user.id, user.username or "", user.first_name or "Бака")

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

    if lvl <= 20:

        return "Враг №1 💢", 0.10, PHOTO_ANGRY

    elif lvl <= 40:

        return "Знакомый бака 😐", 0.08, PHOTO_ANGRY

    elif lvl <= 60:

        return "Почти друг 😳", 0.05, PHOTO_SHY

    elif lvl <= 85:

        return "Тайный краш 💕", 0.02, PHOTO_SHY

    else:

        return "Любимчик Момо 💖", 0.00, PHOTO_LOVE

 

def make_hearts_bar(current: int, target: int, length: int = 6) -> str:

    if target <= 0:

        return "❤️" * length

    filled = int(round(length * min(max(current / target, 0.0), 1.0)))

    return "❤️" * filled + "🖤" * (length - filled)

 

def make_stars_bar(current: int, target: int, length: int = 10) -> str:

    filled = int(round(length * min(max(current / target, 0.0), 1.0)))

    return "⭐" * filled + "☆" * (length - filled)

 

def main_menu(user_id: int):

    buttons = [

        [KeyboardButton(text="🎀 Профиль и Стата"), KeyboardButton(text="🎁 Промокод")],

        [KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="⭐ Вывод звезд")],

        [KeyboardButton(text="🏆 Топ игроков")]

    ]

    if user_id == ADMIN_ID:

        buttons.append([KeyboardButton(text="👑 Админ-панель")])

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

        [InlineKeyboardButton(text="💾 Скачать базу (Бэкап)", callback_data="adm_backup")],

        [InlineKeyboardButton(text="📥 Загрузить базу", callback_data="adm_restore")]

    ])

 

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

    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user.id else None

 

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,)) as cursor:

            exists = await cursor.fetchone()

        if not exists:

            await db.execute(

                "INSERT INTO users (user_id, username, first_name, balance, affection_lvl, affection_xp, referrer_id) VALUES (?, ?, ?, 0, 1, 0, ?)",

                (user.id, user.username or "", user.first_name or "Бака", ref_id)

            )

            await db.commit()

            if ref_id:

                async with aiosqlite.connect(DB_NAME) as db2:

                    await db2.execute("UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1 WHERE user_id = ?", (ref_id,))

                    await db2.commit()

                lvl, _, up = await add_affection_xp(ref_id, 25)

                try:

                    await bot.send_message(ref_id, f"Х-хм! Новый реферал: <b>+30 BAKA</b> и <b>+25 XP</b> к симпатии!", parse_mode="HTML")

                except Exception:

                    pass

 

    welcome_text = (

        "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\n"

        "Я — <b>Цундере Момо</b>.\n\n"

        "<blockquote>💬 Болтай со мной в чате (я ИИ!)\n"

        "💕 Качай 100 уровней симпатии (комиссия падает с 10% до 0%)\n"

        "⭐ Выводи звезды с 1 уровня от 1000 BAKA (50 ⭐)</blockquote>"

    )

    if PHOTO_ANGRY:

        await message.answer_photo(PHOTO_ANGRY, caption=welcome_text, reply_markup=main_menu(user.id), parse_mode="HTML")

    else:

        await message.answer(welcome_text, reply_markup=main_menu(user.id), parse_mode="HTML")

 

async def build_profile_card(user_id: int) -> tuple[str, str]:

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT balance, affection_lvl, affection_xp, referrals_count FROM users WHERE user_id = ?", (user_id,)) as cur:

            row = await cur.fetchone()

            bal, lvl, xp, refs = row if row else (0, 1, 0, 0)

        async with db.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (bal,)) as cur:

            rank_pos = (await cur.fetchone())[0] + 1

        async with db.execute("SELECT COUNT(*) FROM users") as cur:

            total_users = (await cur.fetchone())[0]

 

    stars = round(bal / 20, 2)

    rank_name, fee, photo_id = get_rank_and_fee(lvl)

    req_xp = xp_needed_for_level(lvl) if lvl < 100 else 0

    hearts = make_hearts_bar(xp, req_xp) if lvl < 100 else "❤️❤️❤️❤️❤️❤️"

    stars_bar = make_stars_bar(bal, 1000)

 

    text = (

        f"📊 <b>СТАТИСТИКА ИГРОКА</b>\n"

        f"<blockquote>"

        f"💰 Баланс: <code>{bal} BAKA</code> │ ⭐ <code>{stars}</code>\n"

        f"💕 Симпатия: <code>{lvl}/100 ур.</code> │ 🎖 Ранг: <b>{rank_name}</b>\n"

        f"👥 Друзей: <code>{refs}</code> │ 💸 Комиссия: <code>{int(fee*100)}%</code>\n"

        f"🏆 Место в топе: <code>#{rank_pos} из {total_users}</code>"

        f"</blockquote>\n\n"

        f"💓 <b>До {min(100, lvl + 1)} уровня симпатии:</b>\n"

        f"{hearts} ({xp}/{req_xp} XP)\n\n"

        f"✨ <b>Прогресс до вывода (50 ⭐):</b>\n"

        f"{stars_bar} ({bal}/1000)"

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

        async with db.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,)) as cur:

            last_daily = (await cur.fetchone())[0]

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

        async with db.execute("SELECT last_pet FROM users WHERE user_id = ?", (user_id,)) as cur:

            last_pet = (await cur.fetchone())[0]

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

        async with db.execute("SELECT first_name, balance, affection_lvl FROM users ORDER BY balance DESC LIMIT 10") as cur:

            top_bal = await cur.fetchall()

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

        if not promo or promo[1] <= 0:

            await message.answer("Неверный код или закончились активации!")

        else:

            await db.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))

            await db.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code))

            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[0], user_id))

            await db.commit()

            await message.answer(f"Начислила <b>{promo[0]} BAKA</b>! 🌸", parse_mode="HTML")

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

 

# --- АДМИНКА (ПО КНОПКЕ И ПО КОМАНДЕ /admin) ---

@dp.message(Command("admin"))

@dp.message(F.text == "👑 Админ-панель")

async def open_admin(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(f"⛔ Доступ запрещен. Твой ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

        return

    await message.answer("👑 <b>Админ-панель Момо:</b>", reply_markup=admin_menu(), parse_mode="HTML")

 

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

        await call.message.answer_document(FSInputFile(DB_NAME), caption="💾 Бэкап базы")

    await call.answer()

 

@dp.callback_query(F.data == "adm_restore")

async def adm_restore(call: CallbackQuery, state: FSMContext):

    if call.from_user.id == ADMIN_ID:

        await call.message.answer("Отправь файл <code>momo_database.db</code>:", parse_mode="HTML")

        await state.set_state(BotStates.admin_upload_db)

    await call.answer()

 

@dp.message(BotStates.admin_upload_db, F.document)

async def adm_restore_process(message: Message, state: FSMContext):

    if message.from_user.id == ADMIN_ID:

        file = await bot.get_file(message.document.file_id)

        await bot.download_file(file.file_path, DB_NAME)

        await message.answer("✅ База восстановлена!")

    await state.clear()

 

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

            model="llama-3.3-70b-versatile",

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
