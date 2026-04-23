import asyncio
import requests
from aiogram import F
import sqlite3
import re
import html
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import random
from aiogram import Bot, Dispatcher
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand
)
from aiogram.filters import Command
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("BOT_TOKEN")
API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")

if not token:
    raise RuntimeError("BOT_TOKEN is not set. Add it to environment variables.")
if not API_NINJAS_KEY:
    raise RuntimeError("API_NINJAS_KEY is not set. Add it to environment variables.")

bot = Bot(token=token, timeout=30)
dp = Dispatcher()

calories_cache = {}

# ---------- UI ----------
reminders_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Увімкнути", callback_data="reminders_on"),
        InlineKeyboardButton(text="❌ Вимкнути", callback_data="reminders_off")
    ]
])
reminders_on_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="❌ Вимкнути", callback_data="reminders_off")
    ]
])
reminders_off_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Увімкнути", callback_data="reminders_on")
    ]
])
reset_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Так", callback_data="reset_yes"),
        InlineKeyboardButton(text="❌ Ні", callback_data="reset_no")
    ]
])
suggest_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Виконав", callback_data="suggest_done"),
        InlineKeyboardButton(text="🔁 Інша", callback_data="suggest_retry")
    ]
])
challenge_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Зробив", callback_data="challenge_done"),
        InlineKeyboardButton(text="🔁 Інший челендж", callback_data="challenge_next")
    ]
])

MOTIVATION_QUOTES = [
    "Маленькі кроки щодня = великі результати через місяць.",
    "Ти не завжди маєш бути мотивованим. Будь дисциплінованим.",
    "Кожне тренування - це інвестиція у майбутнього себе.",
    "Не зупиняйся, коли втомився. Зупиняйся, коли завершив.",
    "Прогрес важливіший за ідеальність."
]

HEALTH_TIPS = [
    "Після тренування випий склянку води протягом 15 хвилин.",
    "Роби 5 хвилин розминки перед будь-яким навантаженням.",
    "Сон 7-8 годин пришвидшує відновлення м'язів.",
    "Додай білок до кожного основного прийому їжі.",
    "Краще 20 хвилин руху щодня, ніж 2 години раз на тиждень."
]

FITNESS_CHALLENGES = [
    "30 присідань + 20 відтискувань + планка 40 сек",
    "Швидка прогулянка 25 хв + розтяжка 5 хв",
    "3 кола: 15 випадів, 20 скручувань, планка 30 сек",
    "Біг або швидкий крок 20 хв без зупинок",
    "100 стрибків на місці + 20 присідань + 20 випадів"
]


def style_block(title: str, body: str, icon: str = "✨") -> str:
    safe_title = html.escape(title)
    safe_body = html.escape(body.strip())
    return (
        f"{icon} <b>{safe_title}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{safe_body}"
    )


def generate_workout(goal: str) -> str:
    if "наб" in goal:
        return (random.choice(
            ["💪 Тренування на набір маси:\n"
             "• Відтискування 4x15–20\n"
             "• Присідання 4x25\n"
             "• Випади 3x12\n"
             "• Планка 3x40 сек",
             "💪 Тренування на набір маси:\n"
             "• Відтискування вузькі 4x12\n"
             "• Присідання з паузою 4x20\n"
             "• Ягодичний міст 3x20\n"
             "• Планка 3x45 сек"])

        )
    elif "схуд" in goal or "дієт" in goal:
        return (random.choice([
            "🔥 Тренування на спалювання жиру:\n"
            "• Біг 20–30 хвилин\n"
            "• Бьорпі 3x12\n"
            "• Стрибки 3x40 сек\n"
            "• Планка 3x30 сек",
            "🔥 Тренування на спалювання жиру:\n"
            "• Jumping Jack 4x40 сек\n"
            "• Альпініст 3x30 сек\n"
            "• Присідання 3x25\n"
            "• Планка 3x35 сек"])
        )
    else:
        return (random.choice([
            "🏋️ Універсальне тренування:\n"
            "• Відтискування 3x15\n"
            "• Присідання 3x20\n"
            "• Планка 3x30 сек",
            "🏋️ Універсальне тренування:\n"
            "• Відтискування 3x12\n"
            "• Випади 3x12\n"
            "• Велосипед 3x30 сек\n"
            "• Планка 3x40 сек"])
        )





async def check_missed_days():
    db = get_db()
    cur = db.cursor()

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    cur.execute("""
                SELECT DISTINCT u.user_id
                FROM users u
                         JOIN workouts w ON u.user_id = w.user_id
                WHERE w.date >= ?
                  AND u.reminders_enabled = 1
                """, ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),))

    users = [row[0] for row in cur.fetchall()]

    for uid in users:
        cur.execute("SELECT 1 FROM workouts WHERE user_id=? AND date=?", (uid, yesterday))
        if not cur.fetchone():
            messages = [
                "💪 Вчора пропустив тренування?\nСьогодні новий день! 🔥 /suggest",
                "😴 Відпочив вчора? Повертайся до строю! /today",
                "⚡ Швидкий тест: /suggest → ✅ Виконав!"
            ]
            await bot.send_message(uid, random.choice(messages))

    db.close()
    print("✅Перевірка пропущених днів виконана.")


# ---------- DB ----------
def get_db():
    return sqlite3.connect("sportbot.db")


def init_db():
    db = get_db()
    cur = db.cursor()

    # Создаем users БЕЗ reminders_enabled сначала
    cur.execute("""
                CREATE TABLE IF NOT EXISTS users
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY,
                    height
                    INTEGER,
                    gender
                    TEXT,
                    goal
                    TEXT,
                    weekly_goal
                    INTEGER,
                    current_weight
                    REAL
                    DEFAULT
                    0
                )
                """)

    # ПРОВЕРЯЕМ и добавляем колонку ТОЛЬКО если её нет
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]

    if 'reminders_enabled' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN reminders_enabled INTEGER DEFAULT 1")

    cur.execute("""
                CREATE TABLE IF NOT EXISTS weights
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER,
                    weight
                    REAL,
                    date
                    TEXT
                )
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS workouts
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    user_id
                    INTEGER,
                    text
                    TEXT,
                    date
                    TEXT
                )
                """)

    cur.execute("""
                CREATE TABLE IF NOT EXISTS user_states
                (
                    user_id
                    INTEGER
                    PRIMARY
                    KEY,
                    state
                    TEXT
                )
                """)

    db.commit()
    db.close()


# ---------- UTILS ----------
def set_user_state(user_id: int, state: str):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO user_states (user_id, state)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET state=excluded.state
        """,
        (user_id, state)
    )
    db.commit()
    db.close()


def get_user_state(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT state FROM user_states WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    db.close()
    return row[0] if row else None


def clear_user_state(user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
    db.commit()
    db.close()


def parse_activity_and_duration(text: str):
    raw = text.lower()
    m = re.search(r'(\d+)\s*(хв|хвилин|мин|min)', raw)
    duration = int(m.group(1)) if m else 30

    activity_map = {
        "біг": "running",
        "run": "running",
        "ходьб": "walking",
        "прогулянк": "walking",
        "вело": "bicycling",
        "велосипед": "bicycling",
        "плав": "swimming",
        "відтиск": "push ups",
        "push": "push ups",
        "присідан": "squats",
        "squat": "squats",
        "планк": "plank",
        "випад": "lunges",
        "lunge": "lunges",
        "бурпі": "burpees",
        "бьорпі": "burpees",
        "burpee": "burpees",
        "jumping jack": "jumping jacks",
        "стрибк": "jumping jacks",
        "альпініст": "mountain climbers",
        "mountain": "mountain climbers",
        "скручуван": "sit ups",
        "прес": "sit ups"
    }

    for key, api_activity in activity_map.items():
        if key in raw:
            return api_activity, duration

    return "workout", duration


def calc_calories(text: str) -> int:
    cache_key = text.strip().lower()
    if cache_key in calories_cache:
        return calories_cache[cache_key]

    activity, duration = parse_activity_and_duration(text)

    try:
        response = requests.get(
            "https://api.api-ninjas.com/v1/caloriesburned",
            params={"activity": activity, "duration": duration},
            headers={"X-Api-Key": API_NINJAS_KEY},
            timeout=8
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                total = data[0].get("total_calories")
                if total is not None:
                    value = int(round(float(total)))
                    calories_cache[cache_key] = value
                    return value
    except Exception:
        pass

    # Fallback estimate when API is unavailable or activity wasn't matched
    text = cache_key
    m = re.search(r'(\d+)\s*(хв|хвилин|мин|min)', text)
    if m:
        value = int(m.group(1)) * 8  # rough estimate
        calories_cache[cache_key] = value
        return value

    if 'x' in text or 'х' in text:
        calories_cache[cache_key] = 30
        return 30

    calories_cache[cache_key] = 0
    return 0


def calculate_streak(dates):
    used = set(dates)
    streak = 0
    today = datetime.now().date()

    while True:
        day = today - timedelta(days=streak)
        if day.strftime("%Y-%m-%d") in used:
            streak += 1
        else:
            break
    return streak


# ---------- RESET ----------
@dp.message(Command("reset"))
async def reset_profile(message: Message):
    await message.answer(
        "Видалити профіль і всі дані?",
        reply_markup=reset_kb
    )


@dp.callback_query(lambda c: c.data == "reset_yes")
async def reset_yes(callback: CallbackQuery):
    uid = callback.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM workouts WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM weights WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))

    db.commit()
    db.close()

    await callback.message.edit_text("Профіль повністю видалено.")


@dp.callback_query(lambda c: c.data == "reset_no")
async def reset_no(callback: CallbackQuery):
    await callback.message.edit_text("Скасування.")


# ---------- COMMANDS ----------
@dp.message(Command("start"))
async def start(message: Message):
    text = style_block(
        "SportBot",
        "/profile — профіль\n"
        "/edit_profile — змінити профіль\n"
        "/workout — записати тренування\n"
        "/today — сьогодні\n"
        "/stats — статистика\n"
        "/weight — вага\n"
        "/reset — видалити все\n"
        "/weight_stats — статистика ваги\n"
        "/suggest — запропонувати тренування\n"
        "/set_goal — встановити мету на тиждень\n"
        "/reminders — нагадування\n"
        "/goal — показати мету на тиждень\n"
        "/motivate — мотивація\n"
        "/tip — корисна порада\n"
        "/challenge — челендж дня",
        icon="🏁"
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("profile"))
async def profile(message: Message):
    uid = message.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT height, gender, goal, current_weight FROM users WHERE user_id=?",
        (uid,)
    )
    profile_row = cur.fetchone()
    db.close()

    if not profile_row or not profile_row[0]:
        set_user_state(uid, "profile")
        await message.answer(
            "Введи профіль:\n"
            "Зріст, стать, мета\n"
            "Приклад: 165, ч, набрати масу"
        )
        return

    h, g, goal, current_weight = profile_row  # ← 4 змінні!
    weight_text = f"{current_weight:.1f} кг" if current_weight and current_weight > 0 else "не вказана"

    await message.answer(
        style_block(
            "Профіль",
            f"📏 Зріст: {h} см\n"
            f"🧍 Стать: {g}\n"
            f"⚖️ Вага: {weight_text}\n"
            f"🎯 Мета: {goal}",
            icon="👤"
        ),
        parse_mode="HTML"
    )


@dp.message(Command("edit_profile"))
async def edit_profile(message: Message):
    set_user_state(message.from_user.id, "profile")
    await message.answer(
        "Зріст, стать, мета\n"
        "Приклад: 170, ж, схуднути"
    )


@dp.message(Command("set_goal"))
async def set_goal(message: Message):
    set_user_state(message.from_user.id, "weekly_goal")
    await message.answer(
        "Введи мету на тиждень (кількість днів тренувань)\n"
        "Приклад: 4"
    )


@dp.message(Command("goal"))
async def goal(message: Message):
    uid = message.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT weekly_goal FROM users WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()

    if not row or not row[0] or row[0] < 1:
        db.close()
        await message.answer("Мета не задана. Використовуй /set_goal")
        return

    weekly_goal = int(row[0])

    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT COUNT(DISTINCT date) FROM workouts WHERE user_id=? AND date>=?",
        (uid, week_ago)
    )
    done = cur.fetchone()[0] or 0
    db.close()

    progress = min(int(done / weekly_goal * 100), 100)

    blocks_total = 10
    blocks_done = int(progress / 10)
    bar = "█" * blocks_done + "░" * (blocks_total - blocks_done)

    status = "🔥 Чудово" if done >= weekly_goal else "⏳ Продовжуй"

    await message.answer(
        style_block(
            "Мета на тиждень",
            f"🎯 Ціль: {weekly_goal}\n"
            f"✅ Виконано: {done}\n"
            f"📈 Прогрес: {progress}% {bar}\n"
            f"{status}",
            icon="🗓️"
        ),
        parse_mode="HTML"
    )


@dp.message(Command("reminders"))
async def reminders(message: Message):
    uid = message.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, reminders_enabled)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (uid,)
    )
    cur.execute(
        "SELECT reminders_enabled FROM users WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()
    status = bool(row[0]) if row else True
    db.commit()
    db.close()

    if status:
        await message.answer(
            "🔔 Нагадування вже увімкнені.\n\nХочеш вимкнути?",
            reply_markup=reminders_on_kb
        )
    else:
        await message.answer(
            "🔕 Нагадування вже вимкнені.\n\nХочеш увімкнути?",
            reply_markup=reminders_off_kb
        )


@dp.callback_query(lambda c: c.data == "reminders_on")
async def reminders_on(callback: CallbackQuery):
    uid = callback.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, reminders_enabled)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (uid,)
    )
    cur.execute(
        "UPDATE users SET reminders_enabled=1 WHERE user_id=?",
        (uid,)
    )
    db.commit()
    db.close()

    await callback.message.edit_text(
        "🔔 Нагадування УВІМКНЕНІ!\n\n"
        "Отримувати мотивацію щодня при пропуску тренування? 💪"
    )
    await callback.answer("Увімкнено!")


@dp.callback_query(lambda c: c.data == "reminders_off")
async def reminders_off(callback: CallbackQuery):
    uid = callback.from_user.id
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO users (user_id, reminders_enabled)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO NOTHING
        """,
        (uid,)
    )
    cur.execute(
        "UPDATE users SET reminders_enabled=0 WHERE user_id=?",
        (uid,)
    )
    db.commit()
    db.close()

    await callback.message.edit_text(
        "🔕 Нагадування ВИМКНЕНІ\n\n"
        "Ти босс, тренуйся за настроєм! 😎"
    )
    await callback.answer("Вимкнено!")


@dp.message(Command("suggest"))
async def suggest(message: Message):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT goal FROM users WHERE user_id=?", (message.from_user.id,))
    row = cur.fetchone()
    db.close()

    if not row or not row[0]:
        await message.answer("Спочатку задай мету в профілі (/profile).")
        return

    text = generate_workout(row[0])
    await message.answer(text, reply_markup=suggest_kb)


@dp.message(Command("motivate"))
async def motivate(message: Message):
    quote = random.choice(MOTIVATION_QUOTES)
    await message.answer(
        style_block("Мотивація", f"💬 {quote}", icon="🚀"),
        parse_mode="HTML"
    )


@dp.message(Command("tip"))
async def tip(message: Message):
    tip_text = random.choice(HEALTH_TIPS)
    await message.answer(
        style_block("Порада дня", f"💡 {tip_text}", icon="🧠"),
        parse_mode="HTML"
    )


@dp.message(Command("challenge"))
async def challenge(message: Message):
    challenge_text = random.choice(FITNESS_CHALLENGES)
    await message.answer(
        style_block("Челендж дня", f"🔥 {challenge_text}", icon="🏆"),
        parse_mode="HTML",
        reply_markup=challenge_kb
    )


@dp.callback_query(F.data == "suggest_retry")
async def suggest_retry(callback: CallbackQuery):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT goal FROM users WHERE user_id=?", (callback.from_user.id,))
    row = cur.fetchone()
    db.close()

    if not row or not row[0]:
        await callback.answer("Немає мети", show_alert=True)
        return

    text = generate_workout(row[0])
    await callback.message.answer(text, reply_markup=suggest_kb)
    await callback.answer()


@dp.callback_query(F.data == "suggest_done")
async def suggest_done(callback: CallbackQuery):
    await callback.answer("OK")
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    workout_text = callback.message.text.split("\n", 1)[1]

    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT 1 FROM workouts WHERE user_id=? AND date=?",
        (uid, today)
    )
    if cur.fetchone():
        db.close()
        await callback.answer("Сьогодні вже зараховано")
        return

    for line in workout_text.split("\n"):
        if line.startswith("•"):
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, line[2:], today)
            )

    db.commit()
    db.close()

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Тренування збережено"
    )


@dp.callback_query(F.data == "challenge_next")
async def challenge_next(callback: CallbackQuery):
    challenge_text = random.choice(FITNESS_CHALLENGES)
    await callback.message.edit_text(
        style_block("Челендж дня", f"🔥 {challenge_text}", icon="🏆"),
        parse_mode="HTML",
        reply_markup=challenge_kb
    )
    await callback.answer("Новий челендж 💪")


@dp.callback_query(F.data == "challenge_done")
async def challenge_done(callback: CallbackQuery):
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    challenge_text = callback.message.text

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM workouts WHERE user_id=? AND date=? AND text=?",
        (uid, today, challenge_text)
    )
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
            (uid, challenge_text, today)
        )
        db.commit()
    db.close()

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Челендж зараховано!",
        parse_mode="HTML"
    )
    await callback.answer("Круто! Так тримати 🔥")


@dp.message(Command("workout"))
async def workout(message: Message):
    set_user_state(message.from_user.id, "workout")
    await message.answer(
        "Введи тренування.\n"
        "Можна через кому:\n"
        "Біг 30 хвилин, Відтискування 4x20"
    )


@dp.message(Command("weight"))
async def weight(message: Message):
    set_user_state(message.from_user.id, "weight")
    await message.answer("Введи вагу (кг)")


@dp.message(Command("weight_stats"))
async def weight_stats(message: Message):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT weight, date FROM weights WHERE user_id=? ORDER BY date DESC LIMIT 7",
        (message.from_user.id,)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer("Вага ще не записувалася.")
        return

    text = "⚖️ Вага (останні записи):\n"
    for w, d in rows:
        text += f"{d}: {w} кг\n"

    await message.answer(text)


# ---------- TODAY ----------
@dp.message(Command("today"))
async def today(message: Message):
    db = get_db()
    cur = db.cursor()

    today_date = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT text FROM workouts WHERE user_id=? AND date=?",
        (message.from_user.id, today_date)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer("Сьогодні тренувань немає.")
        return

    total_cal = sum(calc_calories(r[0]) for r in rows)
    text = "\n".join(f"• {r[0]}" for r in rows)

    await message.answer(
        style_block(
            "Сьогоднішні тренування",
            f"{text}\n\n🔥 Витрачено: ~{total_cal} ккал",
            icon="🏋️"
        ),
        parse_mode="HTML"
    )


# ---------- STATS ----------
@dp.message(Command("stats"))
async def stats(message: Message):
    db = get_db()
    cur = db.cursor()
    uid = message.from_user.id

    cur.execute(
        "SELECT date, text FROM workouts WHERE user_id=? ORDER BY date DESC",
        (uid,)
    )
    rows = cur.fetchall()
    db.close()

    if not rows:
        await message.answer("Тренувань немає.")
        return

    dates = [d for d, _ in rows]
    streak = calculate_streak(dates)

    week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")

    total_cal = sum(calc_calories(t) for _, t in rows)
    week_cal = sum(calc_calories(t) for d, t in rows if d >= week_ago)

    text = (
        f"📊 Статистика\n"
        f"Днів тренування: {len(set(dates))}\n"
        f"Серія: {streak}\n"
        f"🔥 Калорій всього: ~{total_cal}\n"
        f"🔥 За 7 днів: ~{week_cal}\n\n"
        f"Останні:\n"
    )

    for d, t in rows[:5]:
        text += f"{d}: {t}\n"

    await message.answer(
        style_block("Статистика", text.replace("📊 Статистика\n", "").strip(), icon="📊"),
        parse_mode="HTML"
    )


# ---------- INPUT ----------
@dp.message()
async def handle_input(message: Message):
    if not message.text:
        await message.answer("Поки що працюю лише з текстом. Спробуй команду /start")
        return

    if message.text.startswith("/"):
        return

    uid = message.from_user.id
    state = get_user_state(uid)

    if not state:
        await message.answer("Я на зв'язку 👋 Використай /start, щоб побачити команди.")
        return

    if state == "weekly_goal":
        try:
            goal = int(message.text)

            db = get_db()
            cur = db.cursor()

            cur.execute(
                """
                INSERT INTO users (user_id, weekly_goal)
                VALUES (?, ?) ON CONFLICT(user_id)
                DO
                UPDATE SET weekly_goal=excluded.weekly_goal
                """,
                (uid, goal)
            )

            db.commit()
            db.close()

            await message.answer("Мета тижня збережена.")
            clear_user_state(uid)
        except:
            await message.answer("Введи число.")
        return

    # WEIGHT
    if state == "weight":
        try:
            w = float(message.text)
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "INSERT INTO weights (user_id, weight, date) VALUES (?, ?, ?)",
                (uid, w, datetime.now().strftime("%Y-%m-%d"))
            )

            cur.execute(
                "UPDATE users SET current_weight = ? WHERE user_id = ?",
                (w, uid)
            )
            db.commit()
            db.close()

            await message.answer("Вагу збережено.")
            clear_user_state(uid)
        except:
            await message.answer("Введи число.")
        return

    # PROFILE
    if state == "profile":
        try:
            h, g, goal = map(str.strip, message.text.split(",", 2))
            h = int(h)
            g = g.lower()
            if g == "ч":
                g = "чоловік👨"
            elif g == "ж":
                g = "жінка👩"
            db = get_db()
            cur = db.cursor()
            cur.execute(
                """
                INSERT INTO users (user_id, height, gender, goal)
                VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO
                UPDATE SET
                    height=excluded.height,
                    gender=excluded.gender,
                    goal=excluded.goal
                """,
                (uid, h, g, goal)
            )
            db.commit()
            db.close()

            await message.answer("Профіль збережено.")
            clear_user_state(uid)
        except:
            await message.answer("Формат: 165, ч, мета")

    # WORKOUT
    if state == "workout":
        exercises = [x.strip() for x in message.text.split(",") if x.strip()]
        db = get_db()
        cur = db.cursor()

        for ex in exercises:
            cur.execute(
                "INSERT INTO workouts (user_id, text, date) VALUES (?, ?, ?)",
                (uid, ex, datetime.now().strftime("%Y-%m-%d"))
            )

        db.commit()
        db.close()

        await message.answer(f"Збережено: {len(exercises)}")
        clear_user_state(uid)


# ---------- RUN ----------
async def main():
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_missed_days, 'cron', hour=9, minute=0)  # 9:00 кожноденно
    scheduler.start()
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="profile", description="Профіль"),
        BotCommand(command="edit_profile", description="Змінити профіль"),
        BotCommand(command="workout", description="Тренування"),
        BotCommand(command="today", description="Сьогодні"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="weight", description="Вага"),
        BotCommand(command="reset", description="Видалити все"),
        BotCommand(command="weight_stats", description="Статистика ваги"),
        BotCommand(command="suggest", description="Запропонувати тренування"),
        BotCommand(command="set_goal", description="Встановити мету на тиждень"),
        BotCommand(command="goal", description="Показати мету на тиждень"),
        BotCommand(command="reminders", description="Нагадування"),
        BotCommand(command="motivate", description="Мотивація"),
        BotCommand(command="tip", description="Корисна порада"),
        BotCommand(command="challenge", description="Челендж дня")
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())