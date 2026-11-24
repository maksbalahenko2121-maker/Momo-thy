import json, aiosqlite

from db import DB_NAME

 

def build_150_achievements():

    achs = []

    for i in range(1, 31):

        target_lvl = 100 if i == 30 else min(100, i * 3)

        achs.append((f"lvl_{i}", f"Сердце Момо #{i}", f"Достигнуть {target_lvl} уровня симпатии", "lvl", target_lvl, 15 + i * 2, 100 + i * 50))

    for i in range(1, 31):

        target_msg = i * 50 if i <= 10 else (i * 250 if i <= 20 else i * 1000)

        achs.append((f"msg_{i}", f"Болтун #{i}", f"Написать {target_msg} сообщений Момо", "msgs", target_msg, 10 + i, 50 + i * 20))

    for i in range(1, 26):

        target_bal = i * 100 if i <= 10 else (i * 300 if i <= 20 else i * 1000)

        achs.append((f"bal_{i}", f"Копилка Баки #{i}", f"Накопить {target_bal} BAKA на балансе", "bal", target_bal, 10 + i, 80 + i * 30))

    for i in range(1, 26):

        target_pet = i * 5 if i <= 10 else i * 15

        achs.append((f"pet_{i}", f"Нежные руки #{i}", f"Погладить Момо {target_pet} раз", "pets", target_pet, 12 + i, 60 + i * 25))

    for i in range(1, 21):

        target_feed = i * 5 if i <= 10 else i * 15

        achs.append((f"feed_{i}", f"Шеф-повар Бенто #{i}", f"Покормить Момо {target_feed} раз", "feeds", target_feed, 15 + i, 70 + i * 30))

    for i in range(1, 21):

        target_ref = i if i <= 10 else i * 3

        achs.append((f"ref_{i}", f"Амбассадор Момо #{i}", f"Пригласить {target_ref} друзей", "refs", target_ref, 25 + i * 5, 150 + i * 50))

    return achs

 

ACHIEVEMENTS = build_150_achievements()

 

async def check_and_grant_achievements(uid: int):

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT affection_lvl, balance, total_msgs, total_pets, total_feeds, referrals_count, unlocked_achs FROM users WHERE user_id = ?", (uid,))).fetchone()

        if not row: return [], 0

        lvl, bal, msgs, pets, feeds, refs, unlocked_j = row

        unlocked = set(json.loads(unlocked_j or "[]"))

 

        stats = {"lvl": lvl, "bal": bal, "msgs": msgs, "pets": pets, "feeds": feeds, "refs": refs}

        newly = []

        bonus_baka, bonus_xp = 0, 0

 

        for aid, title, desc, stype, target, rew_b, rew_xp in ACHIEVEMENTS:

            if aid not in unlocked and stats.get(stype, 0) >= target:

                unlocked.add(aid)

                newly.append((title, rew_b, rew_xp))

                bonus_baka += rew_b

                bonus_xp += rew_xp

 

        if newly:

            await db.execute("UPDATE users SET balance = balance + ?, unlocked_achs = ? WHERE user_id = ?", (bonus_baka, json.dumps(list(unlocked)), uid))

            await db.commit()

    return newly, bonus_xp
