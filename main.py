import asyncio, os, sys, time, random, shutil, logging, subprocess

from datetime import datetime

import aiosqlite

 

try:

    from groq import AsyncGroq

except ImportError:

    subprocess.check_call([sys.executable, "-m", "pip", "install", "groq"])

    from groq import AsyncGroq

 

from aiogram import Bot, Dispatcher, F

from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from aiogram.filters import CommandStart, Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

 

# --- ВСТАВЬ СВОИ ДАННЫЕ СЮДА ---

BOT_TOKEN = "8835996385:AAHXGJfH4TewLUFIDNXrBtdomKT1plizfcg"

ADMIN_ID = 6921885296  # <-- ВСЕ ЦИФРЫ ТВОЕГО ID ИЗ @userinfobot

GROQ_API_KEY = "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"

 

# --- КАРТИНКИ МОМО (file_id) ---

PHOTO_ANGRY = "AgACAgIAAxkBAAKhBmsDmSnWaGVkGdUe9mjAIa52FH89AAINHWsbVAEgSNRj-CUMv7u5AQADAgADeQADPQQ"

PHOTO_SHY = "AgACAgIAAxkBAAKgyWsDlBJhJZadRThIyR-G1GsrVGtxAAIKHWsbVAEgSMKrd1cCVVXkAQADAgADeQADPQQ"

PHOTO_LOVE = "AgACAgIAAxkBAAKgy2sDlBkS44k46CTYNhZITcHje09gAAILHWsbVAEgSLzZ6nmSWbItAQADAgADeQADPQQ"

 

DATA_DIR = os.getenv("DATA_DIR", "/app/data")

try:

    os.makedirs(DATA_DIR, exist_ok=True)

except Exception:

    DATA_DIR = "."

DB_NAME = os.path.join(DATA_DIR, "momo_database.db")

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY and "ВСТАВЬ" not in GROQ_API_KEY else None

ai_cooldown, chat_xp_cooldown = {}, {}

 

MOMO_TIPS = [

    "Болтай со мной в ЛС или позови по имени в чате — за общение капает опыт симпатии!",

    "Каждые 10 уровней комиссия на вывод падает, а на 86+ уровне она станет 0%!",

    "Нажимай «☀️ Поздороваться» раз в сутки, иначе я решу, что ты про меня забыл, бака!",

    "Каждые 3 часа меня можно погладить — только не растрепай мне волосы!",

    "За каждого приглашенного друга ты получишь +30 BAKA и +25 XP к нашим отношениям.",

    "Добавь меня в общий чат — я буду отвечать всем, кто напишет «Момо»!",

    "На каждом новом уровне симпатии открывается уникальная фича в профиле!",

    "Вывод звезд доступен с 1 уровня от 1000 BAKA (50 ⭐)."

]

 

LEVEL_FEATURES = {

    1: "Право находиться в одном чате с Момо", 5: "Момо запомнила твой ник (почти)",

    10: "Комиссия 9% + статус «Терпимый»", 15: "Разрешение здороваться первым",

    20: "Комиссия 8% + иммунитет к ворчанию", 25: "Момо тайно проверяет твой профиль",

    30: "Комиссия 7% + мягкие ответы", 40: "Комиссия 6% + статус «Почти друг»",

    50: "Комиссия 5% + дегустатор бенто 🍱", 60: "Комиссия 4% + Момо краснеет",

    70: "Комиссия 3% + статус «Особенный бака»", 80: "Комиссия 2% + право на комплименты",

    86: "Комиссия на вывод 0% навсегда! 💎", 95: "Момо почти готова признаться...",

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

 

def val0(row, default=0):

    return row[0] if row and row[0] is not None else default

 

async def init_db():

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("PRAGMA journal_mode=WAL;")

        await db.execute(f"CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER DEFAULT 0, affection_lvl INTEGER DEFAULT 1, affection_xp INTEGER DEFAULT 0, referrer_id INTEGER, referrals_count INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0, last_pet INTEGER DEFAULT 0, joined_at INTEGER DEFAULT {now_ts})")

        for col, d in [("affection_lvl", "INTEGER DEFAULT 1"), ("affection_xp", "INTEGER DEFAULT 0"), ("joined_at", f"INTEGER DEFAULT {now_ts}")]:

            try: await db.execute(f"ALTER TABLE users ADD COLUMN {col} {d}")

            except Exception: pass

        await db.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT, members_count INTEGER DEFAULT 0)")

        await db.execute("CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")

        await db.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, code TEXT)")

        await db.execute("CREATE TABLE IF NOT EXISTS settings (key PRIMARY KEY, value TEXT)")

        await db.execute("INSERT OR IGNORE INTO settings VALUES ('sub_enabled', '0'), ('sub_channel', '')")

        await db.commit()

 

async def get_setting(key: str):

    async with aiosqlite.connect(DB_NAME) as db:

        return val0(await (await db.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone(), None)

 

async def set_setting(key: str, value: str):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("REPLACE INTO settings VALUES (?, ?)", (key, value))

        await db.commit()

 

async def ensure_user(user):

    async with aiosqlite.connect(DB_NAME) as db:

        if not await (await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user.id,))).fetchone():

            await db.execute("INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)", (user.id, user.username or "", user.first_name or "Бака", int(time.time())))

            await db.commit()

 

def xp_needed_for_level(lvl: int) -> int:

    return 50 + (lvl * 10)

 

async def add_affection_xp(user_id: int, xp_amount: int):

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT affection_lvl, affection_xp FROM users WHERE user_id = ?", (user_id,))).fetchone()

        lvl, xp = row if row else (1, 0)

        if lvl >= 100: return 100, 0, False

        xp += xp_amount

        up = False

        while lvl < 100 and xp >= xp_needed_for_level(lvl):

            xp -= xp_needed_for_level(lvl)

            lvl += 1

            up = True

        if lvl == 100: xp = 0

        await db.execute("UPDATE users SET affection_lvl = ?, affection_xp = ? WHERE user_id = ?", (lvl, xp, user_id))

        await db.commit()

        return lvl, xp, up

 

def get_rank_and_fee(lvl: int):

    ranks = [(10,"Враг №1 💢",0.10,PHOTO_ANGRY),(20,"Терпимый бака 😒",0.09,PHOTO_ANGRY),(30,"Знакомый 😐",0.08,PHOTO_ANGRY),(40,"Собеседник 🙂",0.07,PHOTO_ANGRY),(50,"Почти друг 😳",0.06,PHOTO_SHY),(60,"Близкий друг 😊",0.05,PHOTO_SHY),(70,"Тайный краш 💕",0.04,PHOTO_SHY),(80,"Особый человек 💓",0.03,PHOTO_SHY),(86,"Почти любимый 💗",0.02,PHOTO_SHY)]

    for lim, name, fee, ph in ranks:

        if lvl < lim: return name, fee, ph

    return "Любимчик Момо 💖", 0.00, PHOTO_LOVE

 

def make_hearts_bar(cur: int, trg: int, length: int = 6) -> str:

    if trg <= 0: return "❤️" * length

    filled = int(round(length * min(max(cur / trg, 0.0), 1.0)))

    return "❤️" * filled + "🖤" * (length - filled)

 

def main_menu():

    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎀 Профиль и Стата"), KeyboardButton(text="🎁 Промокод")],[KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="⭐ Вывод звезд")],[KeyboardButton(text="🏆 Топ игроков")]], resize_keyboard=True)

 

def profile_inline_kb():

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="☀️ Поздороваться", callback_data="act_daily"), InlineKeyboardButton(text="✨ Погладить", callback_data="act_pet")],[InlineKeyboardButton(text="🔄 Обновить стату", callback_data="act_refresh"), InlineKeyboardButton(text="⭐ Вывести", callback_data="act_withdraw")]])

 

def admin_menu():

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Пульс проекта", callback_data="adm_stats")],[InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],[InlineKeyboardButton(text="🎟 Промокод", callback_data="adm_promo")],[InlineKeyboardButton(text="🔒 ОП подписка", callback_data="adm_sub")],[InlineKeyboardButton(text="💾 Скачать базу", callback_data="adm_backup")]])

 

@dp.message(F.document)

async def auto_restore_db(message: Message):

    if message.from_user.id != ADMIN_ID or message.chat.type != "private" or not message.document.file_name or not message.document.file_name.endswith(".db"): return

    try:

        if os.path.exists(DB_NAME): shutil.copy2(DB_NAME, DB_NAME + ".bak")

        file = await bot.get_file(message.document.file_id)

        await bot.download_file(file.file_path, DB_NAME)

        await init_db()

        async with aiosqlite.connect(DB_NAME) as db:

            u_cnt = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 0)

            t_baka = val0(await (await db.execute("SELECT SUM(balance) FROM users")).fetchone(), 0)

        await message.reply(f"✅ <b>База восстановлена!</b>\n👤 Игроков: <b>{u_cnt}</b> | 💰 Банк: <code>{t_baka} BAKA</code>", parse_mode="HTML")

    except Exception as e:

        if os.path.exists(DB_NAME + ".bak"): shutil.copy2(DB_NAME + ".bak", DB_NAME)

        await message.reply(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")

 

@dp.message(F.photo)

async def get_photo_id(message: Message):

    if message.from_user.id == ADMIN_ID and message.chat.type == "private":

        await message.reply(f"🖼 <code>{message.photo[-1].file_id}</code>", parse_mode="HTML")

 

@dp.my_chat_member()

async def on_chat_member(event):

    if event.chat.type in ["group", "supergroup"]:

        async with aiosqlite.connect(DB_NAME) as db:

            if event.new_chat_member.status in ["member", "administrator"]:

                try: cnt = await bot.get_chat_member_count(event.chat.id)

                except Exception: cnt = 0

                await db.execute("REPLACE INTO chats VALUES (?, ?, ?)", (event.chat.id, event.chat.title, cnt))

                if ADMIN_ID: await bot.send_message(ADMIN_ID, f"🔔 Новый чат: <b>{event.chat.title}</b> ({cnt} чел.)", parse_mode="HTML")

            elif event.new_chat_member.status in ["left", "kicked"]:

                await db.execute("DELETE FROM chats WHERE chat_id = ?", (event.chat.id,))

            await db.commit()

 

@dp.message(CommandStart())

async def cmd_start(message: Message):

    if message.chat.type != "private": return

    user = message.from_user

    args = message.text.split()

    ref_id = int(args) if len(args) > 1 and args.isdigit() and int(args) != user.id else None

    async with aiosqlite.connect(DB_NAME) as db:

        if not await (await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user.id,))).fetchone():

            await db.execute("INSERT INTO users (user_id, username, first_name, referrer_id, joined_at) VALUES (?, ?, ?, ?, ?)", (user.id, user.username or "", user.first_name or "Бака", ref_id, int(time.time())))

            if ref_id: await db.execute("UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1 WHERE user_id = ?", (ref_id,))

            await db.commit()

            if ref_id:

                await add_affection_xp(ref_id, 25)

                try: await bot.send_message(ref_id, "Х-хм! Новый реферал: <b>+30 BAKA</b> и <b>+25 XP</b>!", parse_mode="HTML")

                except Exception: pass

    txt = "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\nЯ — <b>Цундере Момо</b>.\n\n<blockquote>💬 Болтай со мной в чате (я ИИ!)\n💕 Качай 100 уровней симпатии\n⭐ Выводи звезды с 1 уровня от 1000 BAKA (50 ⭐)</blockquote>"

    if PHOTO_ANGRY: await message.answer_photo(PHOTO_ANGRY, caption=txt, reply_markup=main_menu(), parse_mode="HTML")

    else: await message.answer(txt, reply_markup=main_menu(), parse_mode="HTML")

 

async def build_profile_card(user_id: int):

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl, affection_xp, referrals_count, joined_at FROM users WHERE user_id = ?", (user_id,))).fetchone()

        bal, lvl, xp, refs, joined_at = row if row else (0, 1, 0, 0, now_ts)

        rank_pos = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (bal,))).fetchone(), 0) + 1

        total_users = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 1)

    joined_at = joined_at or now_ts

    days_known = max(1, (now_ts - joined_at) // 86400 + 1)

    date_str = datetime.fromtimestamp(joined_at).strftime("%d.%m.%Y")

    rank_name, fee, photo_id = get_rank_and_fee(lvl)

    req_xp = xp_needed_for_level(lvl) if lvl < 100 else 0

    hearts = make_hearts_bar(xp, req_xp) if lvl < 100 else "❤️❤️❤️❤️❤️❤️"

    xp_line = f"{hearts} ({xp}/{req_xp} XP)" if lvl < 100 else f"{hearts} (MAX)"

    text = (

        f"📊 <b>СТАТИСТИКА ИГРОКА</b>\n"

        f"<blockquote>💰 Баланс: <code>{bal} BAKA</code> │ ⭐ <code>{round(bal/20, 2)}</code>\n"

        f"💕 Симпатия: <code>{lvl}/100 ур.</code> │ 🎖 Ранг: <b>{rank_name}</b>\n"

        f"👥 Друзей: <code>{refs}</code> │ 💸 Комиссия: <code>{int(fee*100)}%</code>\n"

        f"🏆 Место в топе: <code>#{rank_pos} из {total_users}</code></blockquote>\n\n"

        f"✨ <b>Фича {lvl} уровня:</b> <i>{get_level_feature(lvl)}</i>\n"

        f"💓 <b>До {min(100, lvl + 1)} ур.:</b> {xp_line}\n\n"

        f"📅 <b>Первое знакомство:</b> {days_known} дн. вместе (с {date_str})\n"

        f"💡 <i>Подсказка: {random.choice(MOMO_TIPS)}</i>"

    )

    return text, photo_id

 

@dp.message(F.text == "🎀 Профиль и Стата")

async def profile_msg(message: Message):

    await ensure_user(message.from_user)

    text, photo_id = await build_profile_card(message.from_user.id)

    if photo_id: await message.answer_photo(photo_id, caption=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

    else: await message.answer(text, reply_markup=profile_inline_kb(), parse_mode="HTML")

 

@dp.callback_query(F.data == "act_refresh")

async def cb_refresh(call: CallbackQuery):

    text, _ = await build_profile_card(call.from_user.id)

    try:

        if call.message.photo: await call.message.edit_caption(caption=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

        else: await call.message.edit_text(text=text, reply_markup=profile_inline_kb(), parse_mode="HTML")

    except Exception: pass

    await call.answer("Обновлено!")

 

@dp.callback_query(F.data == "act_daily")

async def cb_daily(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    await ensure_user(call.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 86400: return await call.answer(f"Уже здоровались! Жди {round((86400-(now-last))/3600,1)} ч. 💢", show_alert=True)

        bonus = random.randint(5, 15)

        await db.execute("UPDATE users SET last_daily = ?, balance = balance + ? WHERE user_id = ?", (now, bonus, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 15)

    await call.answer(f"+{bonus} BAKA и +15 XP!" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_refresh(call)

 

@dp.callback_query(F.data == "act_pet")

async def cb_pet(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    await ensure_user(call.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_pet FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 10800: return await call.answer(f"Убери руки! Жди {int((10800-(now-last))/60)} мин. 😳", show_alert=True)

        await db.execute("UPDATE users SET last_pet = ? WHERE user_id = ?", (now, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 10)

    await call.answer("Н-не трогай меня, бака! (+10 XP)" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_refresh(call)

@dp.callback_query(F.data == "act_withdraw")

async def cb_withdraw(call: CallbackQuery, state: FSMContext):

    await call.answer()

    await withdraw_logic(call.from_user.id, call.message, state)

 

@dp.message(F.text == "🏆 Топ игроков")

async def top_players(message: Message):

    async with aiosqlite.connect(DB_NAME) as db:

        top = await (await db.execute("SELECT user_id, username, first_name, balance, affection_lvl FROM users ORDER BY balance DESC LIMIT 10")).fetchall()

    medals = ["🥇", "🥈", "🥉"]

    lines = []

    for i, (uid, uname, fname, bal, lvl) in enumerate(top):

        prefix = medals[i] if i < 3 else f"{i + 1}."

        clean_name = (fname or "Бака").replace("<", "").replace(">", "").replace("&", "")

        link = f"https://t.me{uname}" if uname else f"tg://user?id={uid}"

        lines.append(f'{prefix} <a href="{link}"><b>{clean_name}</b></a> — <code>{bal} BAKA</code> (💕 {lvl} ур.)')

    await message.answer(f"🏆 <b>Топ-10 богачей Момо:</b>\n\n<blockquote>{chr(10).join(lines) or 'Пусто'}</blockquote>", parse_mode="HTML", disable_web_page_preview=True)
 

@dp.message(F.text == "💌 Позвать друзей")

async def referrals(message: Message):

    me = await bot.get_me()

    await message.answer(f"Зови друзей, бака! 🌸\n<blockquote>∙ <b>+30 BAKA</b> и <b>+25 XP</b> за каждого</blockquote>\n\n🔗 <code>https://t.me{me.username}?start={message.from_user.id}</code>", parse_mode="HTML")

 

@dp.message(F.text == "🎁 Промокод")

async def promo_start(message: Message, state: FSMContext):

    await message.answer("Вводи промокод:")

    await state.set_state(BotStates.waiting_promo)

 

@dp.message(BotStates.waiting_promo)

async def promo_process(message: Message, state: FSMContext):

    code, uid = message.text.strip(), message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        if await (await db.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (uid, code))).fetchone():

            await state.clear()

            return await message.answer("Ты уже вводил этот код! 💢")

        promo = await (await db.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (code,))).fetchone()

        if not promo or promo <= 0:

            await message.answer("Неверный код или закончились активации!")

        else:

            await db.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))

            await db.execute("INSERT INTO used_promos VALUES (?, ?)", (uid, code))

            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo, uid))

            await db.commit()

            await message.answer(f"Начислила <b>{promo} BAKA</b>! 🌸", parse_mode="HTML")

    await state.clear()

 

async def check_subscription(user_id: int):

    if await get_setting("sub_enabled") != "1": return True, ""

    ch = await get_setting("sub_channel")

    if not ch: return True, ""

    try:

        m = await bot.get_chat_member(chat_id=ch, user_id=user_id)

        return (m.status in ["member", "administrator", "creator"]), ch

    except Exception: return True, ""

 

async def withdraw_logic(user_id: int, message: Message, state: FSMContext):

    ok, ch = await check_subscription(user_id)

    if not ok: return await message.answer(f"Сначала подпишись на {ch}! 💢", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub_again")]]))

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (user_id,))).fetchone()

        bal, lvl = row if row else (0, 1)

    if bal < 1000: return await message.answer(f"У тебя <b>{bal} BAKA</b>. Вывод с 1 уровня от <b>1000 BAKA</b> (50 ⭐)!", parse_mode="HTML")

    _, fee, _ = get_rank_and_fee(lvl)

    await message.answer(f"⭐ <b>Вывод звезд</b>\nБаланс: <b>{bal} BAKA</b> | Комиссия ({lvl} ур.): <b>{int(fee*100)}%</b>\nВведи сумму BAKA (от 1000):", parse_mode="HTML")

    await state.set_state(BotStates.waiting_withdraw)

 

@dp.message(F.text == "⭐ Вывод звезд")

async def withdraw_start(message: Message, state: FSMContext):

    await ensure_user(message.from_user)

    await withdraw_logic(message.from_user.id, message, state)

 

@dp.callback_query(F.data == "check_sub_again")

async def recheck_sub(call: CallbackQuery, state: FSMContext):

    ok, _ = await check_subscription(call.from_user.id)

    if ok:

        await call.message.delete()

        await withdraw_logic(call.from_user.id, call.message, state)

    else: await call.answer("Ты не подписался!", show_alert=True)

 

@dp.message(BotStates.waiting_withdraw)

async def withdraw_process(message: Message, state: FSMContext):

    if not message.text.isdigit() or int(message.text) < 1000: return await message.answer("Введи число от 1000!")

    amount, uid = int(message.text), message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        bal, lvl = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone()

        if amount > bal:

            await state.clear()

            return await message.answer("Не хватает BAKA!")

        _, fee, _ = get_rank_and_fee(lvl)

        stars = round((amount / 20) * (1 - fee), 2)

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, uid))

        await db.commit()

    await message.answer(f"✅ Заявка принята! К выплате: <b>{stars} ⭐</b>", parse_mode="HTML")

    if ADMIN_ID: await bot.send_message(ADMIN_ID, f"💸 Вывод: @{message.from_user.username} (<code>{uid}</code>) ➡️ <b>{stars} ⭐</b>", parse_mode="HTML")

    await state.clear()

 

@dp.message(Command("admin"))

async def open_admin(message: Message):

    if message.from_user.id != ADMIN_ID: return await message.answer(f"⛔ Нет доступа. Твой ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

    await message.answer("👑 <b>Админ-панель Момо:</b>\n<i>(Для восстановления базы просто отправь файл .db сюда)</i>", reply_markup=admin_menu(), parse_mode="HTML")

 

@dp.callback_query(F.data == "adm_stats")

async def adm_stats(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID: return

    async with aiosqlite.connect(DB_NAME) as db:

        u = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 0)

        c = val0(await (await db.execute("SELECT COUNT(*) FROM chats")).fetchone(), 0)

        b = val0(await (await db.execute("SELECT SUM(balance) FROM users")).fetchone(), 0)

        chats = await (await db.execute("SELECT title, members_count FROM chats ORDER BY members_count DESC LIMIT 10")).fetchall()

    clist = "\n".join([f"∙ <b>{x}</b> ({x} чел.)" for x in chats]) or "Нет чатов"

    await call.message.answer(f"📊 ЛС: <b>{u}</b> | Чатов: <b>{c}</b>\n💰 В банке: <code>{b} BAKA</code>\n\n{clist}", parse_mode="HTML")

    await call.answer()

 

@dp.callback_query(F.data == "adm_backup")

async def adm_backup(call: CallbackQuery):

    if call.from_user.id == ADMIN_ID and os.path.exists(DB_NAME): await call.message.answer_document(FSInputFile(DB_NAME), caption="💾 Бэкап базы")

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

    except Exception: await message.answer("❌ Ошибка формата")

    await state.clear()

 

@dp.callback_query(F.data == "adm_sub")

async def adm_sub(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID: return

    st = "ВКЛ ✅" if await get_setting("sub_enabled") == "1" else "ВЫКЛ ❌"

    ch = await get_setting("sub_channel") or "Не задан"

    await call.message.answer(f"🔒 ОП: {st}\nКанал: <code>{ch}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data="toggle_sub")],[InlineKeyboardButton(text="✏️ Канал", callback_data="edit_sub_channel")]]), parse_mode="HTML")

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

        targets = set([r for r in await (await db.execute("SELECT user_id FROM users")).fetchall()] + [r for r in await (await db.execute("SELECT chat_id FROM chats")).fetchall()])

    sent = 0

    for cid in targets:

        try:

            await message.copy_to(cid)

            sent += 1

            await asyncio.sleep(0.05)

        except Exception: pass

    await message.answer(f"✅ Доставлено: <b>{sent}</b>", parse_mode="HTML")

 
chat_memory = {}

 

@dp.message(F.text)

async def ai_chat_handler(message: Message):

    if not message.text or message.text.startswith("/"): return

    if not groq_client:

        if message.chat.type == "private": await message.answer("⚠️ Ключ GROQ_API_KEY не вставлен в main.py!")

        return

    is_priv = message.chat.type == "private"

    me = await bot.get_me()

    if not is_priv and "момо" not in message.text.lower() and f"@{me.username.lower()}" not in message.text.lower() and not (message.reply_to_message and message.reply_to_message.from_user.id == me.id): return

    uid, now = message.from_user.id, time.time()

    if now - ai_cooldown.get(uid, 0) < 3: return

    ai_cooldown[uid] = now

    await ensure_user(message.from_user)

    async with aiosqlite.connect(DB_NAME) as db:

        lvl = val0(await (await db.execute("SELECT affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone(), 1)

 

    is_creator = (uid == ADMIN_ID)

    if is_creator:

        role_info = "С тобой говорит твой Создатель и Хозяин! Ты знаешь, что именно он написал твой код и создал тебя. Веди себя как цундере: снаружи ворчи и делай вид, что не обязана отчитываться, но в глубине души безмерно уважаешь его, слушаешься и боишься огорчить."

    else:

        mood = "грубая ворчливая цундере" if lvl <= 30 else ("смущающаяся цундере" if lvl <= 80 else "влюбленная застенчивая цундере")

        role_info = f"Уровень вашей симпатии: {lvl}/100 ур. ({mood})."

 

    prompt = f"Ты Цундере Момо, аниме-девушка. {role_info} Помни контекст разговора. Отвечай по-русски, коротко (1-3 предложения), эмоционально."

 

    mem_key = f"{message.chat.id}_{uid}"

    history = chat_memory.get(mem_key, [])

    history.append({"role": "user", "content": message.text[:500]})

    history = history[-6:]

 

    try:

        await bot.send_chat_action(message.chat.id, "typing")

        models = await groq_client.models.list()

        bad = ("whisper", "guard", "tts", "orpheus", "playai", "distil")

        valid_ids = [m.id for m in models.data if not any(b in m.id.lower() for b in bad)]

        chosen_model = next((m for m in valid_ids if "llama-3.3" in m or "llama-3.1" in m or "llama3" in m or "qwen" in m or "gemma" in m), valid_ids.pop(0))

        comp = await groq_client.chat.completions.create(

            model=chosen_model,

            messages=[{"role": "system", "content": prompt}] + history,

            max_tokens=200

        )

        reply_text = comp.choices.pop(0).message.content

        history.append({"role": "assistant", "content": reply_text})

        chat_memory[mem_key] = history[-6:]

        await message.reply(reply_text)

    except Exception as e:

        if is_priv and is_creator: await message.answer(f"⚠️ Ошибка ИИ Groq: <code>{e}</code>", parse_mode="HTML")

 

async def main():

    await init_db()

    await dp.start_polling(bot)

 

if __name__ == "__main__":

    asyncio.run(main())
