import os, time, random, asyncio, logging, aiosqlite

from datetime import datetime

from aiogram import Bot, Dispatcher, F

from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.filters import CommandStart

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from db import DB_NAME, val0, init_db, get_setting, ensure_user, xp_needed_for_level, add_affection_xp

from admin_ai import router as admin_ai_router

 

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8835996385:AAHXGJfH4TewLUFIDNXrBtdomKT1plizfcg"

ADMIN_ID = int(os.getenv("ADMIN_ID") or "6921885296")

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

 

MOMO_TIPS = [

    "Болтай со мной — за сообщения капает опыт симпатии!",

    "Пригласи 3 друзей, чтобы снять дневной лимит на общение со мной!",

    "На 86+ уровне комиссия на вывод звезд станет 0%!",

    "Вывод звезд доступен с 1 уровня от 1300 BAKA (65 ⭐)."

]

 

class UserStates(StatesGroup):

    waiting_promo = State()

    waiting_withdraw = State()

 

async def get_rank_and_fee(lvl: int):

    p_angry, p_shy, p_love = await get_setting("photo_angry"), await get_setting("photo_shy"), await get_setting("photo_love")

    ranks = [(10,"Враг №1 💢",0.10,p_angry),(20,"Терпимый бака 😒",0.09,p_angry),(30,"Знакомый 😐",0.08,p_angry),(40,"Собеседник 🙂",0.07,p_angry),(50,"Почти друг 😳",0.06,p_shy),(60,"Близкий друг 😊",0.05,p_shy),(70,"Тайный краш 💕",0.04,p_shy),(80,"Особый человек 💓",0.03,p_shy),(86,"Почти любимый 💗",0.02,p_shy)]

    for lim, name, fee, ph in ranks:

        if lvl < lim: return name, fee, ph

    return "Любимчик Момо 💖", 0.00, p_love

 

def main_menu():

    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎀 Профиль и Стата"), KeyboardButton(text="🎁 Промокод")],[KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="⭐ Вывод звезд")],[KeyboardButton(text="🏆 Топ игроков")]], resize_keyboard=True)

 

def profile_kb():

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="☀️ Поздороваться", callback_data="act_daily"), InlineKeyboardButton(text="✨ Погладить", callback_data="act_pet")],[InlineKeyboardButton(text="🔄 Обновить", callback_data="act_refresh"), InlineKeyboardButton(text="⭐ Вывести", callback_data="act_withdraw")]])

 

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

    ref_arg = args.pop() if len(args) > 1 else ""

    ref_id = int(ref_arg) if ref_arg.isdigit() and int(ref_arg) != user.id else None

    now_ts = int(time.time())

 

    async with aiosqlite.connect(DB_NAME) as db:

        if not await (await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user.id,))).fetchone():

            await db.execute("INSERT INTO users (user_id, username, first_name, referrer_id, joined_at, last_active) VALUES (?, ?, ?, ?, ?, ?)", (user.id, user.username or "", user.first_name or "Бака", ref_id, now_ts, now_ts))

            if ref_id: await db.execute("UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1 WHERE user_id = ?", (ref_id,))

            await db.commit()

            if ref_id:

                await add_affection_xp(ref_id, 25)

                try: await bot.send_message(ref_id, "Х-хм! Новый реферал: <b>+30 BAKA</b> и <b>+25 XP</b>!", parse_mode="HTML")

                except Exception: pass

        else:

            await db.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now_ts, user.id))

            await db.commit()

 

    txt = "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\nЯ — <b>Цундере Момо</b>.\n\n<blockquote>💬 Болтай со мной в чате (я ИИ!)\n💕 Качай 100 уровней симпатии\n⭐ Выводи звезды с 1 уровня от 1300 BAKA (65 ⭐)</blockquote>"

    photo = await get_setting("photo_angry")

    if photo: await message.answer_photo(photo, caption=txt, reply_markup=main_menu(), parse_mode="HTML")

    else: await message.answer(txt, reply_markup=main_menu(), parse_mode="HTML")

async def build_profile(uid: int):

    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl, affection_xp, referrals_count, joined_at FROM users WHERE user_id = ?", (uid,))).fetchone()

        bal, lvl, xp, refs, joined = row if row else (0, 1, 0, 0, now)

        pos = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (bal,))).fetchone(), 0) + 1

        tot = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 1)

    rname, fee, photo = await get_rank_and_fee(lvl)

    req = xp_needed_for_level(lvl) if lvl < 100 else 0

    ai_st = "♾ Безлимит" if refs >= 3 else f"🔒 {refs}/3 друзей"

    txt = (

        f"📊 <b>ПРОФИЛЬ ИГРОКА</b>\n"

        f"<blockquote>💰 Баланс: <code>{bal} BAKA</code> │ ⭐ <code>{round(bal/20, 2)}</code>\n"

        f"💕 Симпатия: <code>{lvl}/100 ур.</code> ({xp}/{req} XP)\n"

        f"🎖 Ранг: <b>{rname}</b> │ 💸 Комиссия: <code>{int(fee*100)}%</code>\n"

        f"👥 Друзей: <code>{refs}</code> ({ai_st}) │ 🏆 Топ: <code>#{pos}/{tot}</code></blockquote>\n\n"

        f"💡 <i>{random.choice(MOMO_TIPS)}</i>"

    )

    return txt, photo

 

@dp.message(F.text == "🎀 Профиль и Стата")

async def prof_msg(message: Message):

    await ensure_user(message.from_user)

    txt, ph = await build_profile(message.from_user.id)

    if ph: await message.answer_photo(ph, caption=txt, reply_markup=profile_kb(), parse_mode="HTML")

    else: await message.answer(txt, reply_markup=profile_kb(), parse_mode="HTML")

 

@dp.callback_query(F.data == "act_refresh")

async def cb_ref(call: CallbackQuery):

    txt, _ = await build_profile(call.from_user.id)

    try:

        if call.message.photo: await call.message.edit_caption(caption=txt, reply_markup=profile_kb(), parse_mode="HTML")

        else: await call.message.edit_text(text=txt, reply_markup=profile_kb(), parse_mode="HTML")

    except Exception: pass

    await call.answer("Обновлено!")

 

@dp.callback_query(F.data == "act_daily")

async def cb_daily(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 86400: return await call.answer(f"Жди {round((86400-(now-last))/3600,1)} ч. 💢", show_alert=True)

        b = random.randint(5, 15)

        await db.execute("UPDATE users SET last_daily = ?, balance = balance + ? WHERE user_id = ?", (now, b, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 15)

    await call.answer(f"+{b} BAKA и +15 XP!" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_ref(call)

 

@dp.callback_query(F.data == "act_pet")

async def cb_pet(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_pet FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 10800: return await call.answer(f"Жди {int((10800-(now-last))/60)} мин. 😳", show_alert=True)

        await db.execute("UPDATE users SET last_pet = ? WHERE user_id = ?", (now, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 10)

    await call.answer("Н-не трогай, бака! (+10 XP)" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_ref(call)

 

@dp.message(F.text == "🏆 Топ игроков")

async def top_msg(message: Message):

    async with aiosqlite.connect(DB_NAME) as db:

        top = await (await db.execute("SELECT user_id, username, first_name, balance, affection_lvl FROM users ORDER BY balance DESC LIMIT 10")).fetchall()

    medals = ["🥇", "🥈", "🥉"]

    lines = []

    for i, (uid, uname, fname, bal, lvl) in enumerate(top):

        p = medals[i] if i < 3 else f"{i+1}."

        cname = (fname or "Бака").replace("<", "").replace(">", "")

        link = f"https://t.me{uname}" if uname else f"tg://user?id={uid}"

        lines.append(f'{p} <a href="{link}"><b>{cname}</b></a> — <code>{bal} BAKA</code> (💕 {lvl} ур.)')

    await message.answer(f"🏆 <b>Топ-10 богачей:</b>\n\n<blockquote>{chr(10).join(lines) or 'Пусто'}</blockquote>", parse_mode="HTML", disable_web_page_preview=True)

 

@dp.message(F.text == "💌 Позвать друзей")

async def ref_msg(message: Message):

    me = await bot.get_me()

    url = f"https://t.me{me.username}?start={message.from_user.id}"

    await message.answer(f"Зови друзей! 🌸\n∙ <b>+30 BAKA</b> и <b>+25 XP</b> за друга\n∙ <b>3 друга</b> = безлимитный чат с Момо!\n\n🔗 <code>{url}</code>", parse_mode="HTML")

 

@dp.message(F.text == "🎁 Промокод")

async def promo_st(message: Message, state: FSMContext):

    await message.answer("Вводи промокод:")

    await state.set_state(UserStates.waiting_promo)

 

@dp.message(UserStates.waiting_promo)

async def promo_pr(message: Message, state: FSMContext):

    code, uid = message.text.strip(), message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        if await (await db.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (uid, code))).fetchone():

            await state.clear(); return await message.answer("Ты уже вводил этот код! 💢")

        promo = await (await db.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (code,))).fetchone()

        if not promo: await message.answer("Неверный код!")

        else:

            rew, left = promo

            if left <= 0: await message.answer("Активации закончились!")

            else:

                await db.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))

                await db.execute("INSERT INTO used_promos VALUES (?, ?)", (uid, code))

                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (rew, uid))

                await db.commit()

                await message.answer(f"Начислила <b>{rew} BAKA</b>! 🌸", parse_mode="HTML")

    await state.clear()

 

async def check_sub(uid: int):

    if await get_setting("sub_enabled") != "1": return True, ""

    ch = await get_setting("sub_channel")

    if not ch: return True, ""

    try: return ((await bot.get_chat_member(ch, uid)).status in ["member", "administrator", "creator"]), ch

    except Exception: return True, ""

 

async def withdraw_logic(uid: int, message: Message, state: FSMContext):

    ok, ch = await check_sub(uid)

    if not ok: return await message.answer(f"Подпишись на {ch}! 💢", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Проверить", callback_data="chk_sub_w")]]))

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone()

        bal, lvl = row if row else (0, 1)

    if bal < 1300: return await message.answer(f"У тебя <b>{bal} BAKA</b>. Вывод от <b>1300 BAKA</b> (65 ⭐)!", parse_mode="HTML")

    _, fee, _ = await get_rank_and_fee(lvl)

    await message.answer(f"⭐ <b>Вывод звезд</b>\nБаланс: <b>{bal} BAKA</b> | Комиссия: <b>{int(fee*100)}%</b>\nВведи сумму (от 1300):", parse_mode="HTML")

    await state.set_state(UserStates.waiting_withdraw)

 

@dp.callback_query(F.data == "act_withdraw")

async def cb_w(call: CallbackQuery, state: FSMContext):

    await call.answer(); await withdraw_logic(call.from_user.id, call.message, state)

 

@dp.message(F.text == "⭐ Вывод звезд")

async def w_start(message: Message, state: FSMContext):

    await ensure_user(message.from_user); await withdraw_logic(message.from_user.id, message, state)

 

@dp.callback_query(F.data == "chk_sub_w")

async def re_sub(call: CallbackQuery, state: FSMContext):

    ok, _ = await check_sub(call.from_user.id)

    if ok: await call.message.delete(); await withdraw_logic(call.from_user.id, call.message, state)

    else: await call.answer("Не подписан!", show_alert=True)

 

@dp.message(UserStates.waiting_withdraw)

async def w_proc(message: Message, state: FSMContext):

    if not message.text.isdigit() or int(message.text) < 1300: return await message.answer("Введи число от 1300 (минимум 65 ⭐)!")

    amt, uid = int(message.text), message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        bal, lvl = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone()

        if amt > bal: await state.clear(); return await message.answer("Не хватает BAKA!")

        _, fee, _ = await get_rank_and_fee(lvl)

        stars = round((amt / 20) * (1 - fee), 2)

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, uid))

        await db.commit()

    await message.answer(f"✅ Заявка принята! К выплате: <b>{stars} ⭐</b>", parse_mode="HTML")

    if ADMIN_ID: await bot.send_message(ADMIN_ID, f"💸 Вывод: @{message.from_user.username} (<code>{uid}</code>) ➡️ <b>{stars} ⭐</b>", parse_mode="HTML")

    await state.clear()

 

dp.include_router(admin_ai_router)

 

async def main():

    await init_db()

    await dp.start_polling(bot, skip_updates=True)

 

if __name__ == "__main__":

    asyncio.run(main())
