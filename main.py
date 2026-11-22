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

from aiogram.filters import CommandStart

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

 

# --- КОНФИГУРАЦИЯ ---

BOT_TOKEN = os.getenv("9297074957:AAEURglfdq6H-Cd9pjPWs9mme6pkG3vSLeE")

ADMIN_ID = int(os.getenv("6921885296", "0"))

GROQ_API_KEY = os.getenv("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")

DB_NAME = "momo_database.db"

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

 

ai_cooldown = {}

chat_xp_cooldown = {}

 

class BotStates(StatesGroup):

    waiting_promo = State()

    waiting_withdraw = State()

    admin_broadcast = State()

    admin_new_promo = State()

    admin_set_sub = State()

    admin_upload_db = State()

 

# --- БАЗА ДАННЫХ ---

async def init_db():

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("""

            CREATE TABLE IF NOT EXISTS users (

                user_id INTEGER PRIMARY KEY,

                username TEXT,

                first_name TEXT,

                balance INTEGER DEFAULT 0,

                affection INTEGER DEFAULT 10,

                referrer_id INTEGER,

                referrals_count INTEGER DEFAULT 0,

                last_daily INTEGER DEFAULT 0,

                last_pet INTEGER DEFAULT 0

            )

        """)

        await db.execute("""

            CREATE TABLE IF NOT EXISTS chats (

                chat_id INTEGER PRIMARY KEY,

                title TEXT,

                members_count INTEGER DEFAULT 0

            )

        """)

        await db.execute("""

            CREATE TABLE IF NOT EXISTS promos (

                code TEXT PRIMARY KEY,

                reward INTEGER,

                uses_left INTEGER

            )

        """)

        await db.execute("""

            CREATE TABLE IF NOT EXISTS used_promos (

                user_id INTEGER,

                code TEXT

            )

        """)

        await db.execute("""

            CREATE TABLE IF NOT EXISTS settings (

                key TEXT PRIMARY KEY,

                value TEXT

            )

        """)

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

                    "INSERT INTO users (user_id, username, first_name, balance, affection) VALUES (?, ?, ?, 0, 10)",

                    (user.id, user.username or "", user.first_name or "Бака")

                )

                await db.commit()

 

def make_progress_bar(current: int, target: int, length: int = 10) -> str:

    ratio = min(max(current / target, 0.0), 1.0)

    filled = int(round(length * ratio))

    return "■" * filled + "□" * (length - filled)

 

def get_affection_status(aff: int) -> tuple[str, float]:

    if aff <= 25:

        return "Враг №1 💢", 0.01

    elif aff <= 60:

        return "Знакомый бака 😐", 0.01

    elif aff <= 90:

        return "Почти друг 😳", 0.01

    else:

        return "Любимчик Момо 💖 (Комиссия 0%)", 0.00

 

def main_menu(user_id: int):

    buttons = [

        [KeyboardButton(text="🎀 Мой профиль"), KeyboardButton(text="🎁 Промокод")],

        [KeyboardButton(text="☀️ Поприветствовать"), KeyboardButton(text="✨ Погладить Момо")],

        [KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="⭐ Вывод звезд")],

        [KeyboardButton(text="🏆 Топ игроков")]

    ]

    if user_id == ADMIN_ID:

        buttons.append([KeyboardButton(text="👑 Админ-панель")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

 

def admin_menu():

    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="📊 Пульс проекта (Статистика)", callback_data="adm_stats")],

        [InlineKeyboardButton(text="📢 Рассылка (ЛС + Чаты)", callback_data="adm_broadcast")],

        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="adm_promo")],

        [InlineKeyboardButton(text="🔒 Обязательная подписка", callback_data="adm_sub")],

        [InlineKeyboardButton(text="💾 Скачать базу (Бэкап)", callback_data="adm_backup")],

        [InlineKeyboardButton(text="📥 Загрузить базу", callback_data="adm_restore")]

    ])

 

@dp.my_chat_member()

async def on_chat_member(event):

    if event.chat.type in ["group", "supergroup"]:

        if event.new_chat_member.status in ["member", "administrator"]:

            try:

                cnt = await bot.get_chat_member_count(event.chat.id)

            except Exception:

                cnt = 0

            async with aiosqlite.connect(DB_NAME) as db:

                await db.execute(

                    "REPLACE INTO chats (chat_id, title, members_count) VALUES (?, ?, ?)",

                    (event.chat.id, event.chat.title, cnt)

                )

                await db.commit()

            if ADMIN_ID:

                await bot.send_message(

                    ADMIN_ID,

                    f"🔔 **Меня добавили в новый чат!**\n"

                    f"📌 Название: **{event.chat.title}**\n"

                    f"👥 Участников: `{cnt}`\n"

                    f"🆔 ID: `{event.chat.id}`",

                    parse_mode="Markdown"

                )

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

                "INSERT INTO users (user_id, username, first_name, balance, affection, referrer_id) VALUES (?, ?, ?, 0, 10, ?)",

                (user.id, user.username or "", user.first_name or "Бака", ref_id)

            )

            if ref_id:

                await db.execute(

                    "UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1, affection = MIN(100, affection + 5) WHERE user_id = ?",

                    (ref_id,)

                )

                try:

                    await bot.send_message(

                        ref_id,

                        "Х-хм! Кто-то перешел по твоей ссылке!\n"

                        "Так уж и быть, держи **30 Бака-коинов** и **+5% к симпатии**. Не зазнавайся!",

                        parse_mode="Markdown"

                    )

                except Exception:

                    pass

            await db.commit()

 

    await message.answer(

        "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\n"

        "Я — **Цундере Момо**. Можешь просто поболтать со мной (я ведь умный ИИ!) или копить **Бака-коины** и менять их на звезды.\n\n"

        "Выбирай, что тебе нужно, только побыстрее!",

        reply_markup=main_menu(user.id),

        parse_mode="Markdown"

    )

 

@dp.message(F.text == "🎀 Мой профиль")

async def profile(message: Message):

    await ensure_user(message.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute(

            "SELECT balance, affection, referrals_count FROM users WHERE user_id = ?",

            (message.from_user.id,)

        ) as cursor:

            bal, aff, refs = await cursor.fetchone()

 

    stars = round(bal / 20, 2)

    status_name, _ = get_affection_status(aff)

    withdraw_bar = make_progress_bar(bal, 1000)

    aff_bar = make_progress_bar(aff, 100)

    pct_withdraw = min(int((bal / 1000) * 100), 100)

 

    await message.answer(

        f"📂 **ДОСЬЕ НА БАКУ #{message.from_user.id}**\n"

        f"├ 💰 Кошелек: **{bal} BAKA** (~{stars} ⭐)\n"

        f"├ 👥 Приведено друзей: **{refs} чел.**\n"

        f"└ 💭 Отношение Момо: **{status_name}**\n\n"

        f"💕 **Шкала симпатии ({aff}%):**\n"

        f"`[{aff_bar}]`\n\n"

        f"⭐ **Прогресс до вывода 50 звезд ({pct_withdraw}%):**\n"

        f"`[{withdraw_bar}]` ({bal} / 1000 BAKA)",

        parse_mode="Markdown"

    )

@dp.message(F.text == "☀️ Поприветствовать")

async def daily_greet(message: Message):

    await ensure_user(message.from_user)

    now = int(time.time())

    user_id = message.from_user.id

 

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT last_daily, affection FROM users WHERE user_id = ?", (user_id,)) as cur:

            last_daily, aff = await cur.fetchone()

 

        if now - last_daily < 86400:

            hours_left = round((86400 - (now - last_daily)) / 3600, 1)

            await message.answer(f"Мы уже здоровались сегодня, склерозник! Приходи через **{hours_left} ч.** 💢", parse_mode="Markdown")

            return

 

        bonus_coins = random.randint(5, 15)

        new_aff = min(100, aff + 3)

        await db.execute(

            "UPDATE users SET last_daily = ?, balance = balance + ?, affection = ? WHERE user_id = ?",

            (now, bonus_coins, new_aff, user_id)

        )

        await db.commit()

 

    await message.answer(

        f"Д-доброе утро, бака! Не подумай, что я тебя ждала...\n"

        f"Ладно, держи на карманные расходы: **+{bonus_coins} BAKA** и **+3% к симпатии** (теперь **{new_aff}%**) 🌸",

        parse_mode="Markdown"

    )

 

@dp.message(F.text == "✨ Погладить Момо")

async def pet_momo(message: Message):

    await ensure_user(message.from_user)

    now = int(time.time())

    user_id = message.from_user.id

 

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT last_pet, affection FROM users WHERE user_id = ?", (user_id,)) as cur:

            last_pet, aff = await cur.fetchone()

 

        if now - last_pet < 10800:

            mins_left = int((10800 - (now - last_pet)) / 60)

            await message.answer(f"Убери руки! Я еще не отошла от прошлого раза! Жди **{mins_left} мин.** 😳", parse_mode="Markdown")

            return

 

        new_aff = min(100, aff + 2)

        await db.execute("UPDATE users SET last_pet = ?, affection = ? WHERE user_id = ?", (now, new_aff, user_id))

        await db.commit()

 

    phrases = [

        "Н-не трогай мою прическу, идиот! Испортишь же... 😳",

        "Х-хм! Ладно, так уж и быть, можешь погладить... но только секунду! 💕",

        "Б-бака! Что ты делаешь у всех на виду?! (но мне приятно...)"

    ]

    await message.answer(f"{random.choice(phrases)}\n\n📈 Симпатия выросла: **+2%** (теперь **{new_aff}%**)", parse_mode="Markdown")

 

@dp.message(F.text == "🏆 Топ игроков")

async def top_players(message: Message):

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT first_name, balance, affection FROM users ORDER BY balance DESC LIMIT 10") as cur:

            top_bal = await cur.fetchall()

 

    lines = []

    medals = ["🥇", "🥈", "🥉"]

    for idx, (name, bal, aff) in enumerate(top_bal):

        prefix = medals[idx] if idx < 3 else f"{idx + 1}."

        safe_name = (name or "Бака").replace("*", "").replace("_", "")

        lines.append(f"{prefix} **{safe_name}** — `{bal} BAKA` (💕 {aff}%)")

 

    text = "\n".join(lines) or "Пока никого нет!"

    await message.answer(f"🏆 **Топ-10 богачей Цундере Момо:**\n\n{text}", parse_mode="Markdown")

 

@dp.message(F.text == "💌 Позвать друзей")

async def referrals(message: Message):

    bot_info = await bot.get_me()

    ref_link = f"https://t.me{bot_info.username}?start={message.from_user.id}"

    await message.answer(

        f"Хочешь больше Бака-коинов? Зови друзей, так уж и быть! 🌸\n\n"

        f"За каждого друга ты получишь:\n"

        f"∙ **+30 Бака-коинов**\n"

        f"∙ **+5% к шкале симпатии**\n\n"

        f"🔗 Твоя личная ссылка (нажми, чтобы скопировать):\n`{ref_link}`",

        parse_mode="Markdown"

    )

 

@dp.message(F.text == "🎁 Промокод")

async def promo_start(message: Message, state: FSMContext):

    await message.answer("Вводи свой промокод, только побыстрее, я не собираюсь ждать вечность!")

    await state.set_state(BotStates.waiting_promo)

 

@dp.message(BotStates.waiting_promo)

async def promo_process(message: Message, state: FSMContext):

    code = message.text.strip()

    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (user_id, code)) as cur:

            if await cur.fetchone():

                await message.answer("Ты уже вводил этот код, склерозник! 💢")

                await state.clear()

                return

 

        async with db.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (code,)) as cur:

            promo = await cur.fetchone()

 

        if not promo or promo[1] <= 0:

            await message.answer("Нет такого промокода или он уже закончился. Не выдумывай!")

        else:

            reward = promo[0]

            await db.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))

            await db.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code))

            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))

            await db.commit()

            await message.answer(f"Ладно, код верный! Начислила тебе **{reward} Бака-коинов** 🌸", parse_mode="Markdown")

    await state.clear()

 

async def check_subscription(user_id: int) -> tuple[bool, str]:

    enabled = await get_setting("sub_enabled")

    channel = await get_setting("sub_channel")

    if enabled != "1" or not channel:

        return True, ""

    try:

        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)

        if member.status in ["member", "administrator", "creator"]:

            return True, channel

        return False, channel

    except Exception:

        return True, ""

 

@dp.message(F.text == "⭐ Вывод звезд")

async def withdraw_start(message: Message, state: FSMContext):

    await ensure_user(message.from_user)

    is_sub, channel = await check_subscription(message.from_user.id)

    if not is_sub:

        await message.answer(

            f"Эй, бака! Сначала подпишись на наш канал ({channel}), а потом уже требуй звезды! 💢",

            reply_markup=InlineKeyboardMarkup(inline_keyboard=[

                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub_again")]

            ])

        )

        return

 

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT balance, affection FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:

            bal, aff = await cur.fetchone()

 

    if bal < 1000:

        await message.answer(

            f"У тебя всего **{bal} Бака-коинов**.\n"

            f"Вывод доступен от **50 звезд** (это **1000 BAKA**). Иди копи! 🌸",

            parse_mode="Markdown"

        )

        return

 

    _, fee = get_affection_status(aff)

    fee_pct = int(fee * 100)

    await message.answer(

        f"⭐ **Обменник Цундере Момо**\n\n"

        f"💰 Твой баланс: **{bal} BAKA**\n"

        f"📌 Курс: `20 BAKA = 1 ⭐`\n"

        f"💸 Твоя комиссия: **{fee_pct}%** (при симпатии 91%+ она 0%)\n\n"

        f"Введи количество **Бака-коинов** для обмена (минимум 1000):",

        parse_mode="Markdown"

    )

    await state.set_state(BotStates.waiting_withdraw)

 

@dp.callback_query(F.data == "check_sub_again")

async def recheck_sub(call: CallbackQuery, state: FSMContext):

    is_sub, _ = await check_subscription(call.from_user.id)

    if is_sub:

        await call.message.delete()

        await withdraw_start(call.message, state)

    else:

        await call.answer("Я же вижу, что ты не подписался, бака!", show_alert=True)

 

@dp.message(BotStates.waiting_withdraw)

async def withdraw_process(message: Message, state: FSMContext):

    if not message.text.isdigit():

        await message.answer("Введи нормальное число, бака!")

        return

 

    amount = int(message.text)

    if amount < 1000:

        await message.answer("Минимум 1000 Бака-коинов (50 звезд)!")

        return

 

    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT balance, affection FROM users WHERE user_id = ?", (user_id,)) as cur:

            bal, aff = await cur.fetchone()

 

        if amount > bal:

            await message.answer("У тебя столько нет! Не пытайся меня обмануть 💢")

            await state.clear()

            return

 

        _, fee = get_affection_status(aff)

        raw_stars = amount / 20

        final_stars = round(raw_stars * (1 - fee), 2)

 

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

        await db.commit()

 

    await message.answer(

        f"✅ **Заявка на вывод принята!**\n"

        f"Списано: **{amount} BAKA**\n"

        f"К получению: **{final_stars} ⭐**\n"

        f"Ожидай, скоро админ всё отправит!",

        parse_mode="Markdown"

    )

    if ADMIN_ID:

        await bot.send_message(

            ADMIN_ID,

            f"💸 **Новая заявка на вывод!**\n"

            f"Юзер: @{message.from_user.username} (`{user_id}`)\n"

            f"Сумма: `{amount} BAKA` ➡️ **{final_stars} ⭐**",

            parse_mode="Markdown"

        )

    await state.clear()

 

# --- АДМИН-ПАНЕЛЬ ---

@dp.message(F.text == "👑 Админ-панель")

async def open_admin(message: Message):

    if message.from_user.id != ADMIN_ID:

        return

    await message.answer("👑 **Панель управления Цундере Момо:**", reply_markup=admin_menu(), parse_mode="Markdown")

 

@dp.callback_query(F.data == "adm_stats")

async def adm_stats(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID:

        return

    async with aiosqlite.connect(DB_NAME) as db:

        users_cnt = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]

        chats_cnt = (await (await db.execute("SELECT COUNT(*) FROM chats")).fetchone())[0]

        total_baka = (await (await db.execute("SELECT SUM(balance) FROM users")).fetchone())[0] or 0

        ready_users = (await (await db.execute("SELECT COUNT(*) FROM users WHERE balance >= 1000")).fetchone())

        ready_sum = (await (await db.execute("SELECT SUM(balance) FROM users WHERE balance >= 1000")).fetchone()) or 0

        async with db.execute("SELECT title, members_count FROM chats ORDER BY members_count DESC LIMIT 10") as cur:

            chats = await cur.fetchall()

 

    chat_list = "\n".join([f"∙ **{c}** ({c} чел.)" for c in chats]) or "Пока нет чатов"

    await call.message.answer(

        f"📊 **ПУЛЬС ПРОЕКТА МОМО**\n\n"

        f"👤 Игроков в ЛС: **{users_cnt}**\n"

        f"💬 Активных чатов: **{chats_cnt}**\n\n"

        f"💰 **Экономический радар:**\n"

        f"├ Всего в обороте: `{total_baka} BAKA` (~{round(total_baka/20, 1)} ⭐)\n"

        f"└ Готовы к выводу (≥1000): **{ready_users} чел.** (на `~{round(ready_sum/20, 1)} ⭐`)\n\n"

        f"🏆 **Топ чатов с ботом:**\n{chat_list}",

        parse_mode="Markdown"

    )

    await call.answer()

 

@dp.callback_query(F.data == "adm_backup")

async def adm_backup(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID:

        return

    if os.path.exists(DB_NAME):

        await call.message.answer_document(FSInputFile(DB_NAME), caption="💾 Полный бэкап базы данных Момо.")

    await call.answer()

 

@dp.callback_query(F.data == "adm_restore")

async def adm_restore(call: CallbackQuery, state: FSMContext):

    if call.from_user.id != ADMIN_ID:

        return

    await call.message.answer("Отправьте файл базы данных (`momo_database.db`), чтобы восстановить все сохранения:")

    await state.set_state(BotStates.admin_upload_db)

    await call.answer()

 

@dp.message(BotStates.admin_upload_db, F.document)

async def adm_restore_process(message: Message, state: FSMContext):

    if message.from_user.id != ADMIN_ID:

        return

    file = await bot.get_file(message.document.file_id)

    await bot.download_file(file.file_path, DB_NAME)

    await message.answer("✅ База данных успешно загружена и обновлена!")

    await state.clear()

 

@dp.callback_query(F.data == "adm_promo")

async def adm_promo(call: CallbackQuery, state: FSMContext):

    if call.from_user.id != ADMIN_ID:

        return

    await call.message.answer("Введите промокод в формате:\n`КОД НАГРАДА КОЛИЧЕСТВО_АКТИВАЦИЙ`\nПример: `MOMO100 100 50`", parse_mode="Markdown")

    await state.set_state(BotStates.admin_new_promo)

    await call.answer()

 

@dp.message(BotStates.admin_new_promo)

async def adm_promo_save(message: Message, state: FSMContext):

    try:

        code, reward, uses = message.text.split()

        async with aiosqlite.connect(DB_NAME) as db:

            await db.execute("REPLACE INTO promos (code, reward, uses_left) VALUES (?, ?, ?)", (code, int(reward), int(uses)))

            await db.commit()

        await message.answer(f"✅ Промокод `{code}` на **{reward} BAKA** ({uses} исп.) создан!", parse_mode="Markdown")

    except Exception:

        await message.answer("❌ Ошибка формата. Пример: `MOMO100 100 50`", parse_mode="Markdown")

    await state.clear()

 

@dp.callback_query(F.data == "adm_sub")

async def adm_sub(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID:

        return

    status = await get_setting("sub_enabled")

    channel = await get_setting("sub_channel") or "Не задан"

    st_text = "ВКЛЮЧЕНА ✅" if status == "1" else "ВЫКЛЮЧЕНА ❌"

    kb = InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="🔄 Вкл / Выкл ОП", callback_data="toggle_sub")],

        [InlineKeyboardButton(text="✏️ Изменить канал", callback_data="edit_sub_channel")]

    ])

    await call.message.answer(

        f"🔒 **Обязательная подписка при выводе:**\n"

        f"Статус: {st_text}\n"

        f"Канал: `{channel}`\n\n"

        f"*(Бот должен быть админом в этом канале)*",

        reply_markup=kb,

        parse_mode="Markdown"

    )

    await call.answer()

 

@dp.callback_query(F.data == "toggle_sub")

async def toggle_sub(call: CallbackQuery):

    cur = await get_setting("sub_enabled")

    new_val = "0" if cur == "1" else "1"

    await set_setting("sub_enabled", new_val)

    await call.answer("Статус подписки изменен!")

    await adm_sub(call)

 

@dp.callback_query(F.data == "edit_sub_channel")

async def edit_sub_channel(call: CallbackQuery, state: FSMContext):

    await call.message.answer("Отправьте юзернейм канала (например `@mychannel`) или его ID (`-100...`):")

    await state.set_state(BotStates.admin_set_sub)

    await call.answer()

 

@dp.message(BotStates.admin_set_sub)

async def save_sub_channel(message: Message, state: FSMContext):

    await set_setting("sub_channel", message.text.strip())

    await message.answer(f"✅ Канал для подписки сохранен: `{message.text.strip()}`", parse_mode="Markdown")

    await state.clear()

 

@dp.callback_query(F.data == "adm_broadcast")

async def adm_broadcast(call: CallbackQuery, state: FSMContext):

    if call.from_user.id != ADMIN_ID:

        return

    await call.message.answer("Отправьте пост (текст, фото или видео), который нужно разослать во все ЛС и чаты:")

    await state.set_state(BotStates.admin_broadcast)

    await call.answer()

 

@dp.message(BotStates.admin_broadcast)

async def adm_broadcast_send(message: Message, state: FSMContext):

    await state.clear()

    await message.answer("⏳ Начинаю рассылку...")

    async with aiosqlite.connect(DB_NAME) as db:

        users = [r for r in await (await db.execute("SELECT user_id FROM users")).fetchall()]

        chats = [r for r in await (await db.execute("SELECT chat_id FROM chats")).fetchall()]

 

    targets = set(users + chats)

    sent = 0

    for chat_id in targets:

        try:

            await message.copy_to(chat_id)

            sent += 1

            await asyncio.sleep(0.05)

        except Exception:

            pass

    await message.answer(f"✅ Рассылка завершена! Доставлено в **{sent}** чатов/ЛС.", parse_mode="Markdown")

 

# --- ЖИВОЙ ИИ ДИАЛОГ С ЦУНДЕРЕ МОМО ---

@dp.message(F.text)

async def ai_chat_handler(message: Message):

    if not groq_client or not message.text:

        return

 

    is_private = message.chat.type == "private"

    text_lower = message.text.lower()

    bot_me = await bot.get_me()

    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_me.id

    is_mentioned = "момо" in text_lower or f"@{bot_me.username.lower()}" in text_lower

 

    if not is_private and not is_mentioned and not is_reply_to_bot:

        return

 

    user_id = message.from_user.id

    now = time.time()

    if now - ai_cooldown.get(user_id, 0) < 4:

        return

    ai_cooldown[user_id] = now

 

    await ensure_user(message.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        async with db.execute("SELECT affection FROM users WHERE user_id = ?", (user_id,)) as cur:

            aff = (await cur.fetchone())

 

        if now - chat_xp_cooldown.get(user_id, 0) > 180 and aff < 100:

            chat_xp_cooldown[user_id] = now

            aff = min(100, aff + 1)

            await db.execute("UPDATE users SET affection = ? WHERE user_id = ?", (aff, user_id))

            await db.commit()

 

    mood_instruction = (

        "Ты очень грубая и ворчливая цундере, называешь собеседника 'бака' и 'идиот'."

        if aff < 30 else

        "Ты классическая цундере: снаружи ворчишь и отнекиваешься, но в глубине души собеседник тебе уже симпатичен."

        if aff < 80 else

        "Ты сильно влюблена в собеседника, но как цундере ужасно смущаешься, заикаешься (например 'Б-бака...') и пытаешься скрыть свою привязанность."

    )

 

    system_prompt = (

        f"Ты — аниме-девушка по имени Цундере Момо, маскот Telegram-бота. "

        f"Уровень твоей симпатии к этому пользователю: {aff}% из 100%. {mood_instruction} "

        f"Отвечай на русском языке, коротко (1-3 предложения), эмоционально, с легкими аниме-реакциями, без длинных лекций."

    )

 

    try:

        await bot.send_chat_action(message.chat.id, "typing")

        completion = await groq_client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {"role": "system", "content": system_prompt},

                {"role": "user", "content": message.text[:500]}

            ],

            max_tokens=180,

            temperature=0.85

        )

        reply_text = completion.choices.message.content

        await message.reply(reply_text)

    except Exception as e:

        logging.error(f"Groq AI error: {e}")

 

async def main():

    await init_db()

    await dp.start_polling(bot)

 

if __name__ == "__main__":

    asyncio.run(main())

