import os, time, aiosqlite

 

DATA_DIR = "."

for candidate in ["/data", "/app/data", "/storage", "/var/data"]:

    try:

        os.makedirs(candidate, exist_ok=True)

        test_file = os.path.join(candidate, ".write_test")

        with open(test_file, "w") as f: f.write("1")

        os.remove(test_file)

        DATA_DIR = candidate

        break

    except Exception:

        continue

 

DB_NAME = os.path.join(DATA_DIR, "momo_database.db")

 

def val0(row, default=0):

    if row:

        first_val, = row

        return first_val if first_val is not None else default

    return default

 

async def init_db():

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("PRAGMA journal_mode=WAL;")

        await db.execute("PRAGMA synchronous=FULL;")

        await db.execute(f"""CREATE TABLE IF NOT EXISTS users (

            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,

            balance INTEGER DEFAULT 0, affection_lvl INTEGER DEFAULT 1, affection_xp INTEGER DEFAULT 0,

            referrer_id INTEGER, referrals_count INTEGER DEFAULT 0,

            last_daily INTEGER DEFAULT 0, last_pet INTEGER DEFAULT 0, last_feed INTEGER DEFAULT {now_ts},

            joined_at INTEGER DEFAULT {now_ts}, last_active INTEGER DEFAULT {now_ts},

            ai_msgs_today INTEGER DEFAULT 0, ai_day INTEGER DEFAULT 0,

            chat_xp_today INTEGER DEFAULT 0, chat_xp_day INTEGER DEFAULT 0,

            glasses_until INTEGER DEFAULT 0, glasses_last_claim INTEGER DEFAULT 0,

            yandere_until INTEGER DEFAULT 0,

            raffle_joined INTEGER DEFAULT 0, raffle_refs INTEGER DEFAULT 0,

            total_msgs INTEGER DEFAULT 0, total_pets INTEGER DEFAULT 0, total_feeds INTEGER DEFAULT 0,

            unlocked_achs TEXT DEFAULT '[]'

        )""")

        cols = [

            ("last_feed", f"INTEGER DEFAULT {now_ts}"), ("last_active", f"INTEGER DEFAULT {now_ts}"),

            ("ai_msgs_today", "INTEGER DEFAULT 0"), ("ai_day", "INTEGER DEFAULT 0"),

            ("chat_xp_today", "INTEGER DEFAULT 0"), ("chat_xp_day", "INTEGER DEFAULT 0"),

            ("glasses_until", "INTEGER DEFAULT 0"), ("glasses_last_claim", "INTEGER DEFAULT 0"),

            ("yandere_until", "INTEGER DEFAULT 0"), ("raffle_joined", "INTEGER DEFAULT 0"),

            ("raffle_refs", "INTEGER DEFAULT 0"), ("total_msgs", "INTEGER DEFAULT 0"),

            ("total_pets", "INTEGER DEFAULT 0"), ("total_feeds", "INTEGER DEFAULT 0"),

            ("unlocked_achs", "TEXT DEFAULT '[]'")

        ]

        for col, d in cols:

            try: await db.execute(f"ALTER TABLE users ADD COLUMN {col} {d}")

            except Exception: pass

 

        await db.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT, members_count INTEGER DEFAULT 0, invite_link TEXT DEFAULT '')")

        try: await db.execute("ALTER TABLE chats ADD COLUMN invite_link TEXT DEFAULT ''")

        except Exception: pass

 

        await db.execute("CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, reward INTEGER, uses_left INTEGER)")

        await db.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, code TEXT)")

        await db.execute("CREATE TABLE IF NOT EXISTS withdrawals (wid INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, amount_baka INTEGER, stars REAL, status TEXT DEFAULT 'pending', created_at INTEGER)")

        await db.execute("CREATE TABLE IF NOT EXISTS settings (key PRIMARY KEY, value TEXT)")

        for k, v in [("sub_enabled", "0"), ("sub_channel", ""), ("photo_angry", ""), ("photo_shy", ""), ("photo_love", ""), ("raffle_active", "0")]:

            await db.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (k, v))

        await db.commit()

 

async def get_setting(key: str) -> str:

    async with aiosqlite.connect(DB_NAME) as db:

        return val0(await (await db.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone(), "")

 

async def set_setting(key: str, value: str):

    async with aiosqlite.connect(DB_NAME) as db:

        await db.execute("REPLACE INTO settings VALUES (?, ?)", (key, value))

        await db.commit()

 

async def ensure_user(user):

    now_ts = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:

        if not await (await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user.id,))).fetchone():

            await db.execute("INSERT INTO users (user_id, username, first_name, last_feed, joined_at, last_active) VALUES (?, ?, ?, ?, ?, ?)", (user.id, user.username or "", user.first_name or "Бака", now_ts, now_ts, now_ts))

        else:

            await db.execute("UPDATE users SET username = ?, first_name = ?, last_active = ? WHERE user_id = ?", (user.username or "", user.first_name or "Бака", now_ts, user.id))

        await db.commit()

 

def xp_needed_for_level(lvl: int) -> int:

    return 1000 + (lvl * 535)

 

async def add_affection_xp(user_id: int, xp_amount: int, is_chat_msg: bool = False):

    today = int(time.time() // 86400)

    async with aiosqlite.connect(DB_NAME) as db:

        row = await (await db.execute("SELECT affection_lvl, affection_xp, chat_xp_today, chat_xp_day FROM users WHERE user_id = ?", (user_id,))).fetchone()

        lvl, xp, c_today, c_day = row if row else (1, 0, 0, 0)

        if lvl >= 100: return 100, 0, False

 

        if c_day != today:

            c_today = 0

 

        if is_chat_msg:

            left = max(0, 750 - c_today)

            xp_amount = min(xp_amount, left)

            if xp_amount <= 0:

                return lvl, xp, False

            c_today += xp_amount

 

        xp += xp_amount

        up = False

        while lvl < 100 and xp >= xp_needed_for_level(lvl):

            xp -= xp_needed_for_level(lvl)

            lvl += 1

            up = True

        if lvl == 100: xp = 0

 

        await db.execute("UPDATE users SET affection_lvl = ?, affection_xp = ?, chat_xp_today = ?, chat_xp_day = ? WHERE user_id = ?", (lvl, xp, c_today, today, user_id))

        await db.commit()

        return lvl, xp, up

