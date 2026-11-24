import os, time, json, random, asyncio, logging, aiosqlite

from aiogram import Bot, Dispatcher, F

from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, FSInputFile

from aiogram.filters import CommandStart

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from db import DB_NAME, val0, init_db, get_setting, ensure_user, xp_needed_for_level, add_affection_xp

from achievements import ACHIEVEMENTS, check_and_grant_achievements

from admin_ai import router as admin_ai_router

 

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8835996385:AAHXGJfH4TewLUFIDNXrBtdomKT1plizfcg"

ADMIN_ID = int(os.getenv("ADMIN_ID") or "6921885296")

 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

 

MOMO_TIPS = [

    "Корми Момо каждые 6 часов, иначе она украдёт от 10 до 30 BAKA!",

    "Пригласи 3 друзей, чтобы снять дневной лимит на общение со мной!",

    "На 86+ уровне комиссия на вывод звезд станет 0%!",

    "Вывод звезд доступен от 1300 BAKA (65 ⭐)."

]

 

class UserStates(StatesGroup):

    waiting_promo = State()

    waiting_withdraw = State()

 

async def apply_hunger_penalty(uid: int) -> int:

    now = int(time.time())

    stolen_total = 0

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, last_feed FROM users WHERE user_id = ?", (uid,))).fetchone()

        if row:

            bal, last_feed = row

            if last_feed and now - last_feed >= 21600:

                periods = (now - last_feed) // 21600

                for _ in range(min(periods, 10)):

                    if bal <= 0: break

                    steal = min(bal, random.randint(10, 30))

                    bal -= steal

                    stolen_total += steal

                new_feed = last_feed + periods * 21600

                await db.execute("UPDATE users SET balance = ?, last_feed = ? WHERE user_id = ?", (bal, new_feed, uid))

                await db.commit()

    return stolen_total

 

async def get_rank_and_fee(lvl: int):

    p_angry, p_shy, p_love = await get_setting("photo_angry"), await get_setting("photo_shy"), await get_setting("photo_love")

    ranks = [(10,"Враг №1 💢",0.10,p_angry),(20,"Терпимый бака 😒",0.09,p_angry),(30,"Знакомый 😐",0.08,p_angry),(40,"Собеседник 🙂",0.07,p_angry),(50,"Почти друг 😳",0.06,p_shy),(60,"Близкий друг 😊",0.05,p_shy),(70,"Тайный краш 💕",0.04,p_shy),(80,"Особый человек 💓",0.03,p_shy),(86,"Почти любимый 💗",0.02,p_shy)]

    for lim, name, fee, ph in ranks:

        if lvl < lim: return name, fee, ph

    return "Любимчик Момо 💖", 0.00, p_love

 

def main_menu():

    return ReplyKeyboardMarkup(keyboard=[

        [KeyboardButton(text="🎀 Профиль и Стата"), KeyboardButton(text="💎 Магазин Stars")],

        [KeyboardButton(text="🏅 Достижения (150)"), KeyboardButton(text="🎉 Розыгрыш")],

        [KeyboardButton(text="💌 Позвать друзей"), KeyboardButton(text="🎁 Промокод")],

        [KeyboardButton(text="⭐ Вывод звезд"), KeyboardButton(text="🏆 Топ игроков")]

    ], resize_keyboard=True)

 

def profile_kb(has_glasses: bool):

    rows = [

        [InlineKeyboardButton(text="🍱 Покормить", callback_data="act_feed"), InlineKeyboardButton(text="✨ Погладить", callback_data="act_pet")],

        [InlineKeyboardButton(text="☀️ Поздороваться", callback_data="act_daily"), InlineKeyboardButton(text="🔄 Обновить", callback_data="act_refresh")]

    ]

    if has_glasses:

        rows.insert(0, [InlineKeyboardButton(text="👓 Собрать доход с очков (+30/ч)", callback_data="act_claim_glasses")])

    return InlineKeyboardMarkup(inline_keyboard=rows)

 

@dp.my_chat_member()

async def on_chat_member(event):

    if event.chat.type in ["group", "supergroup"]:

        async with aiosqlite.connect(DB_NAME) as db:

            if event.new_chat_member.status in ["member", "administrator"]:

                try: cnt = await bot.get_chat_member_count(event.chat.id)

                except Exception: cnt = 0

                link = f"https://t.me{event.chat.username}" if event.chat.username else ""

                if not link:

                    try: link = await bot.export_chat_invite_link(event.chat.id)

                    except Exception: link = ""

                await db.execute("REPLACE INTO chats VALUES (?, ?, ?, ?)", (event.chat.id, event.chat.title, cnt, link))

                await db.commit()

                if ADMIN_ID:

                    link_txt = f'\n🔗 <a href="{link}">Перейти в чат</a>' if link else "\n<i>(Закрытый чат без прав админа)</i>"

                    await bot.send_message(ADMIN_ID, f"🔔 <b>Бота добавили в чат!</b>\nЧат: <b>{event.chat.title}</b> ({cnt} чел.){link_txt}", parse_mode="HTML", disable_web_page_preview=True)

                await bot.send_message(event.chat.id, "Х-хм! Чего уставились, придурки? Я Цундере Момо! 🌸\nЗовите меня по имени «Момо», чтобы поболтать (дайте права админа, чтобы я следила за порядком!).")

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

    raffle_on = await get_setting("raffle_active") == "1"

 

    async with aiosqlite.connect(DB_NAME) as db:

        if not await (await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user.id,))).fetchone():

            await db.execute("INSERT INTO users (user_id, username, first_name, referrer_id, last_feed, joined_at, last_active) VALUES (?, ?, ?, ?, ?, ?, ?)", (user.id, user.username or "", user.first_name or "Бака", ref_id, now_ts, now_ts, now_ts))

            if ref_id:

                await db.execute("UPDATE users SET balance = balance + 30, referrals_count = referrals_count + 1 WHERE user_id = ?", (ref_id,))

                if raffle_on:

                    await db.execute("UPDATE users SET raffle_refs = raffle_refs + 1 WHERE user_id = ? AND raffle_joined = 1", (ref_id,))

            await db.commit()

            if ref_id:

                await add_affection_xp(ref_id, 50)

                await check_and_grant_achievements(ref_id)

                try: await bot.send_message(ref_id, "Х-хм! Новый реферал пришёл по твоей ссылке: <b>+30 BAKA</b> и <b>+50 XP</b>!", parse_mode="HTML")

                except Exception: pass

        else:

            await db.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now_ts, user.id))

            await db.commit()

 

    txt = "Х-хм! Не думай, что я рада тебя видеть, бака! 🌸\nЯ — <b>Цундере Момо</b>.\n\n<blockquote>💬 Болтай со мной в чатах и ЛС\n🍱 Корми каждые 6 часов, иначе украду BAKA!\n⭐ Выводи звезды от 1300 BAKA (65 ⭐)</blockquote>"

    photo = await get_setting("photo_angry")

    if photo: await message.answer_photo(photo, caption=txt, reply_markup=main_menu(), parse_mode="HTML")

    else: await message.answer(txt, reply_markup=main_menu(), parse_mode="HTML")

 

async def build_profile(uid: int):

    stolen = await apply_hunger_penalty(uid)

    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl, affection_xp, referrals_count, last_feed, glasses_until, yandere_until FROM users WHERE user_id = ?", (uid,))).fetchone()

        bal, lvl, xp, refs, l_feed, g_until, y_until = row if row else (0, 1, 0, 0, now, 0, 0)

        pos = val0(await (await db.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (bal,))).fetchone(), 0) + 1

        tot = val0(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone(), 1)

    rname, fee, photo = await get_rank_and_fee(lvl)

    req = xp_needed_for_level(lvl) if lvl < 100 else 0

    ai_st = "♾ Безлимит" if refs >= 3 else f"🔒 {refs}/3 друзей"

    hunger_left = max(0, 21600 - (now - (l_feed or now)))

    h_str = f"{hunger_left // 3600}ч {(hunger_left % 3600) // 60}м" if hunger_left > 0 else "ГОЛОДНА! 💢"

   

    buffs = []

    if g_until > now: buffs.append(f"👓 Розовые очки ({(g_until - now)//3600}ч)")

    if y_until > now: buffs.append(f"🔪 Режим Яндере ({(y_until - now)//60}м)")

    buff_line = f"\n✨ <b>Активно:</b> {', '.join(buffs)}" if buffs else ""

    warn_line = f"\n⚠️ <i>Пока ты спал, голодная Момо украла {stolen} BAKA!</i>\n" if stolen > 0 else ""

 

    txt = (

        f"📊 <b>ПРОФИЛЬ ИГРОКА</b>{warn_line}\n"

        f"<blockquote>💰 Баланс: <code>{bal} BAKA</code> │ ⭐ <code>{round(bal/20, 2)}</code>\n"

        f"💕 Симпатия: <code>{lvl}/100 ур.</code> ({xp}/{req} XP)\n"

        f"🎖 Ранг: <b>{rname}</b> │ 💸 Комиссия: <code>{int(fee*100)}%</code>\n"

        f"🍱 Сытость: <b>{h_str}</b> │ 👥 Друзей: <code>{refs}</code> ({ai_st})\n"

        f"🏆 Место в топе: <code>#{pos}/{tot}</code></blockquote>{buff_line}\n\n"

        f"💡 <i>{random.choice(MOMO_TIPS)}</i>"

    )

    return txt, photo, (g_until > now)

 

@dp.message(F.text == "🎀 Профиль и Стата")

async def prof_msg(message: Message):

    await ensure_user(message.from_user)

    txt, ph, has_g = await build_profile(message.from_user.id)

    if ph: await message.answer_photo(ph, caption=txt, reply_markup=profile_kb(has_g), parse_mode="HTML")

    else: await message.answer(txt, reply_markup=profile_kb(has_g), parse_mode="HTML")

 

@dp.callback_query(F.data == "act_refresh")

async def cb_ref(call: CallbackQuery):

    txt, _, has_g = await build_profile(call.from_user.id)

    try:

        if call.message.photo: await call.message.edit_caption(caption=txt, reply_markup=profile_kb(has_g), parse_mode="HTML")

        else: await call.message.edit_text(text=txt, reply_markup=profile_kb(has_g), parse_mode="HTML")

    except Exception: pass

    await call.answer("Обновлено!")

 

@dp.callback_query(F.data == "act_feed")

async def cb_feed(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_feed FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 7200: return await call.answer("Я ещё не голодна! Покорми через пару часов. 💢", show_alert=True)

        await db.execute("UPDATE users SET last_feed = ?, total_feeds = total_feeds + 1 WHERE user_id = ?", (now, uid))

        await db.commit()

    await add_affection_xp(uid, 30)

    await check_and_grant_achievements(uid)

    await call.answer("🍱 В-вкусно... Не думай, что я благодарна! (+30 XP, таймер голода сброшен)", show_alert=True)

    await cb_ref(call)

 

@dp.callback_query(F.data == "act_claim_glasses")

async def cb_claim_glasses(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT glasses_until, glasses_last_claim FROM users WHERE user_id = ?", (uid,))).fetchone()

        until, last_c = row if row else (0, 0)

        eff_now = min(now, until)

        hours = (eff_now - last_c) // 3600

        if hours < 1: return await call.answer("Ещё не прошёл полный час с последнего сбора!", show_alert=True)

        reward = hours * 30

        new_claim = last_c + hours * 3600

        await db.execute("UPDATE users SET balance = balance + ?, glasses_last_claim = ? WHERE user_id = ?", (reward, new_claim, uid))

        await db.commit()

    await call.answer(f"👓 Собрано +{reward} BAKA за {hours} ч.!", show_alert=True)

    await cb_ref(call)

 

@dp.callback_query(F.data == "act_daily")

async def cb_daily(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 86400: return await call.answer(f"Жди {round((86400-(now-last))/3600,1)} ч. 💢", show_alert=True)

        b = random.randint(5, 15)

        await db.execute("UPDATE users SET last_daily = ?, balance = balance + ? WHERE user_id = ?", (now, b, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 40)

    await call.answer(f"+{b} BAKA и +40 XP!" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_ref(call)

 

@dp.callback_query(F.data == "act_pet")

async def cb_pet(call: CallbackQuery):

    uid, now = call.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        last = val0(await (await db.execute("SELECT last_pet FROM users WHERE user_id = ?", (uid,))).fetchone(), 0)

        if now - last < 10800: return await call.answer(f"Жди {int((10800-(now-last))/60)} мин. 😳", show_alert=True)

        await db.execute("UPDATE users SET last_pet = ?, total_pets = total_pets + 1 WHERE user_id = ?", (now, uid))

        await db.commit()

    lvl, _, up = await add_affection_xp(uid, 25)

    await check_and_grant_achievements(uid)

    await call.answer("Н-не трогай, бака! (+25 XP)" + (f" 🎉 Уровень {lvl}!" if up else ""), show_alert=True)

    await cb_ref(call)

@dp.message(F.text == "💎 Магазин Stars")

async def shop_stars(message: Message):

    kb = InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="👓 Розовые очки на 24ч (+30 BAKA/ч) — 20 ⭐️", callback_data="buy_glasses")],

        [InlineKeyboardButton(text="🔪 Режим «Яндере Момо» на 1 час — 7 ⭐️", callback_data="buy_yandere")]

    ])

    await message.answer(

        "💎 <b>Магазин за Telegram Stars ⭐️</b>\n\n"

        "∙ <b>👓 Розовые очки (20 ⭐️):</b> приносят <b>+30 BAKA каждый час</b> в течение 24 часов.\n"

        "∙ <b>🔪 Яндере Момо (7 ⭐️):</b> на 1 час превращает Момо в безумно ревнивую и одержимую яндере!",

        reply_markup=kb, parse_mode="HTML"

    )

 

@dp.callback_query(F.data.in_(["buy_glasses", "buy_yandere"]))

async def send_star_invoice(call: CallbackQuery):

    is_g = call.data == "buy_glasses"

    await call.message.answer_invoice(

        title="Розовые очки (24 часа)" if is_g else "Режим Яндере Момо (1 час)",

        description="+30 BAKA в час на 24 часа" if is_g else "Одержимый характер Яндере на 60 минут",

        payload=call.data, currency="XTR",

        prices=[LabeledPrice(label="Оплата Stars", amount=20 if is_g else 7)]

    )

    await call.answer()

 

@dp.pre_checkout_query()

async def pre_checkout(q: PreCheckoutQuery):

    await q.answer(ok=True)

 

@dp.message(F.successful_payment)

async def payment_success(message: Message):

    pay = message.successful_payment.invoice_payload

    uid, now = message.from_user.id, int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        if pay == "buy_glasses":

            await db.execute("UPDATE users SET glasses_until = ?, glasses_last_claim = ? WHERE user_id = ?", (now + 86400, now, uid))

            await message.answer("👓 <b>Розовые очки надеты на 24 часа!</b> Заходи в профиль и собирай +30 BAKA каждый час!", parse_mode="HTML")

        elif pay == "buy_yandere":

            await db.execute("UPDATE users SET yandere_until = ? WHERE user_id = ?", (now + 3600, uid))

            await message.answer("🔪 <b>Режим ЯНДЕРЕ активирован на 1 час!</b>\n<i>*хихикнула* Теперь ты никуда от меня не денешься, любимый...</i>", parse_mode="HTML")

        await db.commit()

 

@dp.message(F.text == "🏅 Достижения (150)")

async def achs_msg(message: Message):

    await ensure_user(message.from_user)

    await check_and_grant_achievements(message.from_user.id)

    async with aiosqlite.connect(DB_NAME) as db:

        u_json = val0(await (await db.execute("SELECT unlocked_achs FROM users WHERE user_id = ?", (message.from_user.id,))).fetchone(), "[]")

    unlocked = set(json.loads(u_json))

    lines = [f"🏅 <b>ТВОИ ДОСТИЖЕНИЯ: {len(unlocked)} / 150</b>\n"]

    shown = 0

    for aid, title, desc, _, _, rew_b, _ in ACHIEVEMENTS:

        if aid not in unlocked:

            lines.append(f"🔒 <b>{title}</b> — {desc} (+{rew_b} BAKA)")

            shown += 1

            if shown >= 12: break

    await message.answer("\n".join(lines) + "\n\n<i>Награды за выполненные ачивки начисляются автоматически!</i>", parse_mode="HTML")

 

@dp.message(F.text == "🎉 Розыгрыш")

async def raffle_msg(message: Message):

    await ensure_user(message.from_user)

    if await get_setting("raffle_active") != "1":

        return await message.answer("⏳ Сейчас активных розыгрышей нет. Следи за анонсами!")

    uid = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT raffle_joined, raffle_refs FROM users WHERE user_id = ?", (uid,))).fetchone()

        joined, r_refs = row if row else (0, 0)

        top = await (await db.execute("SELECT first_name, raffle_refs FROM users WHERE raffle_joined = 1 ORDER BY raffle_refs DESC LIMIT 5")).fetchall()

    top_txt = "\n".join([f"{i}. <b>{n}</b> — {c} реф." for i, (n, c) in enumerate(top, 1)]) or "Пока никого"

    kb = None if joined else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎉 Участвовать в розыгрыше!", callback_data="join_raffle")]])

    st_txt = f"✅ Ты участвуешь! Приглашено за конкурс: <b>{r_refs} чел.</b>" if joined else "❌ Ты ещё не нажал кнопку участия!"

    await message.answer(f"🎉 <b>КОНКУРС РЕФОВОДОВ</b>\n\n{st_txt}\n\n🏆 <b>Лидеры конкурса:</b>\n{top_txt}", reply_markup=kb, parse_mode="HTML")

 

@dp.callback_query(F.data == "join_raffle")

async def cb_join_raffle(call: CallbackQuery):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("UPDATE users SET raffle_joined = 1 WHERE user_id = ?", (call.from_user.id,))

        await db.commit()

    await call.answer("🎉 Ты в игре! Теперь приглашай друзей по своей ссылке!", show_alert=True)

    await call.message.delete()

 

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

    await message.answer(f"Зови друзей! 🌸\n∙ <b>+30 BAKA</b> и <b>+50 XP</b> за друга\n∙ <b>3 друга</b> = безлимитный чат с Момо!\n\n🔗 <code>{url}</code>", parse_mode="HTML")

 

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

 

@dp.message(F.text == "⭐ Вывод звезд")

async def w_start(message: Message, state: FSMContext):

    uid = message.from_user.id

    await ensure_user(message.from_user)

    ok, ch = await check_sub(uid)

    if not ok: return await message.answer(f"Подпишись на {ch}! 💢")

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone()

        bal, lvl = row if row else (0, 1)

    if bal < 1300: return await message.answer(f"У тебя <b>{bal} BAKA</b>. Минимальный вывод от <b>1300 BAKA</b> (65 ⭐)!", parse_mode="HTML")

    _, fee, _ = await get_rank_and_fee(lvl)

    await message.answer(f"⭐ <b>Вывод звезд</b>\nБаланс: <b>{bal} BAKA</b> | Комиссия: <b>{int(fee*100)}%</b>\nВведи сумму BAKA (от 1300):", parse_mode="HTML")

    await state.set_state(UserStates.waiting_withdraw)

 

@dp.message(UserStates.waiting_withdraw)

async def w_proc(message: Message, state: FSMContext):

    if not message.text.isdigit() or int(message.text) < 1300: return await message.answer("Введи число от 1300 (минимум 65 ⭐)!")

    amt, uid = int(message.text), message.from_user.id

    uname = message.from_user.username or "без_ника"

    async with aiosqlite.connect(DB_NAME) as db:

        bal, lvl = await (await db.execute("SELECT balance, affection_lvl FROM users WHERE user_id = ?", (uid,))).fetchone()

        if amt > bal: await state.clear(); return await message.answer("Не хватает BAKA!")

        _, fee, _ = await get_rank_and_fee(lvl)

        stars = round((amt / 20) * (1 - fee), 2)

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, uid))

        cur = await db.execute("INSERT INTO withdrawals (user_id, username, amount_baka, stars, created_at) VALUES (?, ?, ?, ?, ?)", (uid, uname, amt, stars, int(time.time())))

        wid = cur.lastrowid

        await db.commit()

    await message.answer(f"✅ Заявка #{wid} принята! Ожидай выплату <b>{stars} ⭐</b>", parse_mode="HTML")

    if ADMIN_ID:

        kb = InlineKeyboardMarkup(inline_keyboard=[[

            InlineKeyboardButton(text="✅ Выплачено", callback_data=f"wpay_{wid}"),

            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wrej_{wid}")

        ]])

        await bot.send_message(ADMIN_ID, f"💸 <b>Новая заявка #{wid}</b>\nОт: @{uname} (<code>{uid}</code>)\nСумма: <code>{amt} BAKA</code> ➡️ <b>{stars} ⭐</b>", reply_markup=kb, parse_mode="HTML")

    await state.clear()

 

async def auto_backup_loop():

    while True:

        await asyncio.sleep(21600)

        if ADMIN_ID and os.path.exists(DB_NAME):

            try: await bot.send_document(ADMIN_ID, FSInputFile(DB_NAME), caption="🛡 Авто-бэкап базы Момо")

            except Exception: pass

 

dp.include_router(admin_ai_router)

 

async def main():

    await init_db()

    asyncio.create_task(auto_backup_loop())

    await dp.start_polling(bot, skip_updates=True)

 

if __name__ == "__main__":

    asyncio.run(main())
