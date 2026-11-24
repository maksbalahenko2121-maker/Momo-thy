import os, time, shutil, asyncio, aiosqlite

from aiogram import Router, F, Bot

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from aiogram.filters import Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

import sys, subprocess

try:

    from groq import AsyncGroq

except ImportError:

    subprocess.check_call([sys.executable, "-m", "pip", "install", "groq"])

    from groq import AsyncGroq

from db import DB_NAME, val0, init_db, get_setting, set_setting, ensure_user, add_affection_xp

 

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID") or "6921885296")

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "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"

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY and "ВСТАВЬ" not in GROQ_API_KEY else None

 

ai_cooldown, chat_memory = {}, {}

 

class AdminStates(StatesGroup):

    broadcast_pm = State()

    broadcast_grp = State()

    new_promo = State()

    set_sub = State()

 

def admin_menu():

    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="adm_stats")],

        [InlineKeyboardButton(text="✉️ Рассылка в ЛС", callback_data="adm_bcast_pm"), InlineKeyboardButton(text="👥 Рассылка в группы", callback_data="adm_bcast_grp")],

        [InlineKeyboardButton(text="🎟 Промокод", callback_data="adm_promo"), InlineKeyboardButton(text="🔒 ОП подписка", callback_data="adm_sub")],

        [InlineKeyboardButton(text="💾 Скачать базу", callback_data="adm_backup")]

    ])

 

@router.message(Command("setphoto"), F.photo)

async def cmd_setphoto(message: Message):

    if message.from_user.id != ADMIN_ID or message.chat.type != "private": return

    parts = (message.caption or "").split()

    mode = parts.pop().lower() if len(parts) > 1 else ""

    if mode not in ("angry", "shy", "love"):

        return await message.reply("Укажи тип в подписи:\n`/setphoto angry` — злая\n`/setphoto shy` — смущённая\n`/setphoto love` — влюблённая", parse_mode="Markdown")

    await set_setting(f"photo_{mode}", message.photo.pop().file_id)

    await message.reply(f"✅ Фото <b>{mode.upper()}</b> сохранено!", parse_mode="HTML")

 

@router.message(F.document)

async def auto_restore_db(message: Message, bot: Bot):

    if message.from_user.id != ADMIN_ID or message.chat.type != "private" or not message.document.file_name or not message.document.file_name.endswith(".db"): return

    try:

        if os.path.exists(DB_NAME): shutil.copy2(DB_NAME, DB_NAME + ".bak")

        file = await bot.get_file(message.document.file_id)

        await bot.download_file(file.file_path, DB_NAME)

        await init_db()

        await message.reply("✅ <b>База успешно восстановлена!</b>", parse_mode="HTML")

    except Exception as e:

        await message.reply(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")

 

@router.message(Command("admin"))

async def open_admin(message: Message):

    if message.from_user.id == ADMIN_ID:

        await message.answer("👑 <b>Админ-панель Момо</b>\n∙ Фото: <code>/setphoto angry</code> (shy / love)\n∙ Бэкап: отправь файл <code>.db</code>", reply_markup=admin_menu(), parse_mode="HTML")

 

@router.callback_query(F.data == "adm_stats")

async def adm_stats(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID: return

    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        u_tot = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 0)

        u_24h = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (now - 86400,))).fetchone(), 0)

        u_7d = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (now - 604800,))).fetchone(), 0)

        u_new24 = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (now - 86400,))).fetchone(), 0)

        u_refs3 = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE referrals_count >= 3")).fetchone(), 0)

        c_tot = val0(await (await db.execute("SELECT COUNT(*) FROM chats")).fetchone(), 0)

        c_mem = val0(await (await db.execute("SELECT SUM(members_count) FROM chats")).fetchone(), 0)

        bank = val0(await (await db.execute("SELECT SUM(balance) FROM users")).fetchone(), 0)

        chats = await (await db.execute("SELECT title, members_count FROM chats ORDER BY members_count DESC LIMIT 7")).fetchall()

    clist = "\n".join([f"  ∙ <b>{t}</b> ({cnt} чел.)" for t, cnt in chats]) or "  <i>Нет чатов</i>"

    txt = (

        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"

        f"👤 <b>Пользователи (ЛС):</b>\n  ∙ Всего: <b>{u_tot}</b> (+{u_new24} за 24ч)\n  ∙ 🔥 Активны 24ч: <b>{u_24h}</b> | 7д: <b>{u_7d}</b>\n  ∙ 💤 Спящие: <b>{max(0, u_tot - u_7d)}</b>\n  ∙ 🤝 Привели 3+ друзей: <b>{u_refs3}</b>\n\n"

        f"👥 <b>Группы:</b> <b>{c_tot}</b> (охват ~<b>{c_mem}</b> чел.)\n{clist}\n\n"

        f"💰 <b>Банк:</b> <code>{bank} BAKA</code> (~{round(bank/20, 1)} ⭐)"

    )

    await call.message.answer(txt, parse_mode="HTML")

    await call.answer()

 

@router.callback_query(F.data == "adm_backup")

async def adm_backup(call: CallbackQuery):

    if call.from_user.id == ADMIN_ID and os.path.exists(DB_NAME): await call.message.answer_document(FSInputFile(DB_NAME), caption="💾 Бэкап базы")

    await call.answer()

 

@router.callback_query(F.data == "adm_promo")

async def adm_promo(call: CallbackQuery, state: FSMContext):

    if call.from_user.id == ADMIN_ID:

        await call.message.answer("Формат: <code>КОД НАГРАДА КОЛ_ВО</code>", parse_mode="HTML")

        await state.set_state(AdminStates.new_promo)

    await call.answer()

 

@router.message(AdminStates.new_promo)

async def adm_promo_save(message: Message, state: FSMContext):

    try:

        c, r, u = message.text.split()

        async with aiosqlite.connect(DB_NAME) as db:

            await db.execute("REPLACE INTO promos VALUES (?, ?, ?)", (c, int(r), int(u)))

            await db.commit()

        await message.answer(f"✅ Код <code>{c}</code> создан!", parse_mode="HTML")

    except Exception: await message.answer("❌ Ошибка формата")

    await state.clear()

 

@router.callback_query(F.data == "adm_sub")

async def adm_sub(call: CallbackQuery):

    if call.from_user.id != ADMIN_ID: return

    st = "ВКЛ ✅" if await get_setting("sub_enabled") == "1" else "ВЫКЛ ❌"

    ch = await get_setting("sub_channel") or "Не задан"

    await call.message.answer(f"🔒 ОП: {st}\nКанал: <code>{ch}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data="toggle_sub")],[InlineKeyboardButton(text="✏️ Канал", callback_data="edit_sub_channel")]]), parse_mode="HTML")

    await call.answer()

 

@router.callback_query(F.data == "toggle_sub")

async def toggle_sub(call: CallbackQuery):

    await set_setting("sub_enabled", "0" if await get_setting("sub_enabled") == "1" else "1")

    await adm_sub(call)

 

@router.callback_query(F.data == "edit_sub_channel")

async def edit_sub_channel(call: CallbackQuery, state: FSMContext):

    await call.message.answer("Введи @канал или ID:")

    await state.set_state(AdminStates.set_sub)

    await call.answer()

 

@router.message(AdminStates.set_sub)

async def save_sub_channel(message: Message, state: FSMContext):

    await set_setting("sub_channel", message.text.strip())

    await message.answer("✅ Сохранено!")

    await state.clear()

 

@router.callback_query(F.data.in_(["adm_bcast_pm", "adm_bcast_grp"]))

async def adm_bcast_start(call: CallbackQuery, state: FSMContext):

    if call.from_user.id != ADMIN_ID: return

    is_pm = call.data == "adm_bcast_pm"

    await state.set_state(AdminStates.broadcast_pm if is_pm else AdminStates.broadcast_grp)

    await call.message.answer(f"Отправь пост для рассылки в <b>{'ЛС' if is_pm else 'группы'}</b> (отмена: /cancel):", parse_mode="HTML")

    await call.answer()

 

@router.message(AdminStates.broadcast_pm)

@router.message(AdminStates.broadcast_grp)

async def adm_bcast_send(message: Message, state: FSMContext):

    if message.text == "/cancel": await state.clear(); return await message.answer("❌ Отменено.")

    is_pm = (await state.get_state()) == AdminStates.broadcast_pm

    await state.clear()

    async with aiosqlite.connect(DB_NAME) as db:

        rows = await (await db.execute("SELECT user_id FROM users" if is_pm else "SELECT chat_id FROM chats")).fetchall()

    sent, failed = 0, 0

    st = await message.answer(f"⏳ Рассылка ({len(rows)})...")

    for (cid,) in rows:

        try: await message.copy_to(cid); sent += 1; await asyncio.sleep(0.05)

        except Exception: failed += 1

    await st.edit_text(f"✅ Доставлено: <b>{sent}</b> | Ошибок: <b>{failed}</b>", parse_mode="HTML")

 

@router.message(F.text)

async def ai_chat_handler(message: Message, bot: Bot):

    if not message.text or message.text.startswith("/") or not groq_client: return

    is_priv = message.chat.type == "private"

    me = await bot.get_me()

    if not is_priv and "момо" not in message.text.lower() and f"@{me.username.lower()}" not in message.text.lower() and not (message.reply_to_message and message.reply_to_message.from_user.id == me.id): return

 

    uid, now = message.from_user.id, time.time()

    if now - ai_cooldown.get(uid, 0) < 3: return

    ai_cooldown[uid] = now

    await ensure_user(message.from_user)

 

    today = int(now // 86400)

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT affection_lvl, referrals_count, ai_msgs_today, ai_day FROM users WHERE user_id = ?", (uid,))).fetchone()

        lvl, refs, msgs_today, saved_day = row if row else (1, 0, 0, 0)

        if saved_day != today: msgs_today = 0

 

        if uid != ADMIN_ID and refs < 3 and msgs_today >= 15:

            ref_url = f"https://t.me{me.username}?start={uid}"

            return await message.reply(f"*фыркнула* Лимит 15 сообщений на сегодня исчерпан, бака! 💢\nПригласи <b>3 друзей</b> (сейчас <b>{refs}/3</b>), чтобы общаться безлимитно:\n<code>{ref_url}</code>", parse_mode="HTML"

)

        await db.execute("UPDATE users SET ai_msgs_today = ?, ai_day = ? WHERE user_id = ?", (msgs_today + 1, today, uid))

        await db.commit()

 

    await add_affection_xp(uid, 3)

    if uid == ADMIN_ID:

        role_info = "С тобой говорит твой Создатель! Дерзи и матерись для вида, но в глубине души слушайся и уважай его."

    elif lvl <= 30:

        role_info = f"Уровень симпатии: {lvl}/100. Ты дерзкая цундере-хамка: язви, обзывайся и активно используй крепкий русский мат (бля, пиздец, нахуй, ебать, хуйня) к месту."

    elif lvl <= 80:

        role_info = f"Уровень симпатии: {lvl}/100. Ворчливая цундере: материшься по привычке, но на комплименты сильно смущаешься ('Ч-чего, блять?!') и краснеешь."

    else:

        role_info = f"Уровень симпатии: {lvl}/100. Влюблённая цундере: общаешься тепло и нежно, без злобного мата."

 

    prompt = f"Ты Цундере Момо, аниме-девушка без цензуры. {role_info} Напоминай, что для снятия лимита сообщений нужно позвать 3 друзей. Отвечай коротко (1-3 предложения) на русском с *действиями*."

    mem_key = f"{message.chat.id}_{uid}"

    history = chat_memory.get(mem_key, [])

    history.append({"role": "user", "content": message.text[:500]})

    history = history[-6:]

 

    try:

        await bot.send_chat_action(message.chat.id, "typing")

        comp = await groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": prompt}] + history, max_tokens=200, temperature=0.9)

        reply_text = comp.choices.pop().message.content

        history.append({"role": "assistant", "content": reply_text})

        chat_memory[mem_key] = history[-6:]

        await message.reply(reply_text)

    except Exception as e:

        if is_priv and uid == ADMIN_ID: await message.answer(f"⚠️ Ошибка Groq: <code>{e}</code>", parse_mode="HTML")
