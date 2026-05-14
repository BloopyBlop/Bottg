# telegram_fitness_bot.py
import telebot
import os
import json
import math
from datetime import datetime, time, timedelta, date
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, telegram, telebot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    JobQueue,
)

# ====== Настройки ======
# Токен берём из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("8414719305:AAHnGkDNUfVqo0MHgLORR9gi_50GYutqgrM")
if not BOT_TOKEN:
    raise SystemExit("Please set the BOT_TOKEN environment variable.")

DATA_FILE = "fitness_users.json"

# ====== Модели/структуры данных ======
class UserProfile:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.name: Optional[str] = None
        self.gender: Optional[str] = None  # 'male'|'female'|'other'
        self.age: Optional[int] = None
        self.height_cm: Optional[float] = None
        self.weight_kg: Optional[float] = None
        self.calories_per_day: Optional[float] = None  # цель
        self.imt: Optional[float] = None  # BMI
        self.tdee: Optional[float] = None  # суточная потребность
        self.goal: Optional[str] = None  # 'lose_weight'|'maintain'|'gain_muscle'
        self.notification_time: Optional[str] = None  # "HH:MM" 24h
        self.today_menu: Optional[Dict[str, Any]] = None  # меню на сегодня (ИСПРАВЛЕНО)
        self.meals_today_kg: float = 0.0  # суммарное потребление за день
        self.log: Dict[str, Any] = {
            "meals": [],  # [{"name":..., "kcal":..., "time": "..."}]
            "workouts": [],  # [{"name":..., "cal":..., "time": "..."}]
            "date": date.today().isoformat(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "calories_per_day": self.calories_per_day,
            "imt": self.imt,
            "tdee": self.tdee,
            "goal": self.goal,
            "notification_time": self.notification_time,
            "log": self.log,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "UserProfile":
        u = UserProfile(d.get("user_id"))
        u.name = d.get("name")
        u.gender = d.get("gender")
        u.age = d.get("age")
        u.height_cm = d.get("height_cm")
        u.weight_kg = d.get("weight_kg")
        u.calories_per_day = d.get("calories_per_day")
        u.imt = d.get("imt")
        u.tdee = d.get("tdee")
        u.goal = d.get("goal")
        u.notification_time = d.get("notification_time")
        u.log = d.get("log", {"meals": [], "workouts": [], "date": date.today().isoformat()})
        return u

# ====== Хранилище ======
def load_users() -> Dict[int, UserProfile]:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    users = {}
    for uid, d in data.items():
        users[int(uid)] = UserProfile.from_dict(d)
    return users

def save_users(users: Dict[int, UserProfile]):
    data = {uid: u.to_dict() for uid, u in users.items()}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ====== Математика/логика ======
def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100.0
    if height_m <= 0:
        return 0.0
    return weight_kg / (height_m * height_m)

def mh_food_calorie_needs(gender: str, age: int, height_cm: float, weight_kg: float) -> float:
    # Мифлин-Сент Жеор базовая формула
    if gender.lower() in ["male", "m"]:
        s = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        s = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    return max(1000, s)  # не ниже 1000 ккал

def estimate_tdee(bmr: float, activity_factor: float = 1.35) -> float:
    # простой множитель активности (можно расширить)
    return bmr * activity_factor

def plan_options():
    # Пример простых вариантов меню/тренировок
    return {
        "menus": [
            {"name": "Лёгкий день", "calories": 1500},
            {"name": "Средний день", "calories": 1800},
            {"name": "Интенсивный день", "calories": 2100},
        ],
        "workouts": [
            {"name": "Кардио 30 мин + 15 мин силовая", "duration_min": 45},
            {"name": "Интервальная тренировка 20 мин", "duration_min": 20},
            {"name": "Йога 40 мин", "duration_min": 40},
        ],
    }

# ====== Команды/диалоги ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_users()
    uid = user.id
    if uid not in users:
        users[uid] = UserProfile(uid)
    save_users(users)

    await update.message.reply_text(
        "Привет! Я помощник по похудению и тренировкам. "
        "Чтобы начать, введи/укажи базовые данные: рост (см), вес (кг), возраст (лет), пол ('male'/'female'). "
        "Затем можно будет настроить уведомления и увидеть персональные планы."
    )

async def set_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args  # ожидаем: рост вес возраст пол
    users = load_users()
    uid = update.effective_user.id
    if uid not in users:
        users[uid] = UserProfile(uid)

    u = users[uid]

    # Простейшая обработка аргументов
    try:
        if len(args) >= 4:
            u.height_cm = float(args[0])
            u.weight_kg = float(args[1])
            u.age = int(args[2])
            gender = args[3].lower()
            if gender in ["male", "m", "female", "f"]:
                u.gender = "male" if gender in ["male", "m"] else "female"
        else:
            await update.message.reply_text(
                "Пожалуйста, передай аргументы: рост_cm вес_kg возраст пол(male/female)"
            )
            save_users(users)
            return
    except Exception as e:
        await update.message.reply_text(f"Ошибка обработки аргументов: {e}")
        save_users(users)
        return

    # вычисления
    if u.height_cm and u.weight_kg and u.age:
        u.imt = calculate_bmi(u.weight_kg, u.height_cm)
        bmr = mh_food_calorie_needs(u.gender or "male", u.age, u.height_cm, u.weight_kg)
        u.tdee = estimate_tdee(bmr, 1.4)  # средний фактор активности
        # цель по умолчанию: похудение, если не задана
        if not u.goal:
            u.goal = "lose_weight"
        save_users(users)
        await update.message.reply_text(
            f"Данные сохранены.\n"
            f"BMI: {u.imt:.2f}\n"
            f"Основа суточной потребности (BMR): {bmr:.0f} ккал/сут.\n"
            f"Суточная потребность с учетом активности: {u.tdee:.0f} ккал/сут.\n"
            f"Цель: {u.goal}."
        )
    else:
        await update.message.reply_text("Проверьте ввод и повторите.")

async def set_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /set_notifications HH:MM
    time_str = context.args[0] if context.args else None
    if not time_str:
        await update.message.reply_text("Укажи время уведомлений в формате HH:MM (24ч).")
        return
    # простая валидация
    try:
        h, m = map(int, time_str.split(":"))
        assert 0 <= h < 24 and 0 <= m < 60
    except Exception:
        await update.message.reply_text("Неправильный формат времени. Используй HH:MM.")
        return
    uid = update.effective_user.id
    users = load_users()
    if uid not in users:
        users[uid] = UserProfile(uid)
    users[uid].notification_time = f"{time_str}"
    save_users(users)
    await update.message.reply_text(f"Уведомления установлены на {time_str} каждый день.")

async def plan_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users = load_users()
    u = users.get(uid)
    if not u or not (u.height_cm and u.weight_kg and u.age):
        await update.message.reply_text("Пожалуйста, сначала введите профиль: рост/вес/возраст/пол.")
        return
    plans = plan_options()
    # простая генерация дневного плана
    # реальная версия — подгружает данные из научно-обоснованных источников
    menus = plans["menus"]
    workouts = plans["workouts"]
    today_menu = menus[0]  # можно выбирать по дню/цели
    workout_today = workouts[0]

    u.today_menu = {
        "date": date.today().isoformat(),
        "menu": today_menu,
        "workout": workout_today,
    }
    save_users(users)
    await update.message.reply_text(
        f"План на сегодня:\n"
        f"Меню: {today_menu['name']} - {today_menu['calories']} kcal\n"
        f"Упражнение: {workout_today['name']} ({workout_today['duration_min']} мин)\n"
        f"Приятного занятия!"
    )

async def log_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /log_meal название калории
    uid = update.effective_user.id
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Используйте: /log_meal <название> <ккал>")
        return
    name = " ".join(args[:-1])
    try:
        kcal = float(args[-1])
    except:
        await update.message.reply_text("Укажите число калорий.")
        return
    users = load_users()
    u = users.get(uid)
    if not u:
        await update.message.reply_text("Сначала создайте профиль (/start).")
        return
    entry = {"name": name, "kcal": kcal, "time": datetime.now().strftime("%H:%M")}
    u.log.setdefault("meals", []).append(entry)
    u.log["date"] = date.today().isoformat()
    u.meals_today_kg += kcal  # простая сумма калорий
    save_users(users)
    await update.message.reply_text(f"Добавлено: {name} - {kcal} kcal")

async def log_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Используйте: /log_workout <название> <калории_сожжено>")
        return
    name = " ".join(args[:-1])
    try:
        kcal = float(args[-1])
    except:
        kcal = 0.0
    users = load_users()
    u = users.get(uid)
    if not u:
        await update.message.reply_text("Сначала создайте профиль (/start).")
        return
    entry = {"name": name, "calories_burned": kcal, "time": datetime.now().strftime("%H:%M")}
    u.log.setdefault("workouts", []).append(entry)
    save_users(users)
    await update.message.reply_text(f"Занесено: {name} - {kcal} ккал сожжено")

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users = load_users()
    u = users.get(uid)
    if not u:
        await update.message.reply_text("Сначала создайте профиль (/start).")
        return
    consumed = sum(item.get("kcal", 0) for item in u.log.get("meals", []))
    burned = sum(item.get("calories_burned", 0) for item in u.log.get("workouts", []))
    net = consumed - burned
    # пример оценочного времени до цели (упрощённый пример)
    if u.tdee and u.calories_per_day:
        remaining = u.calories_per_day - consumed
        estimate_days = max(1, int(remaining / max(1, (u.tdee - (u.calories_per_day or u.tdee)) + 1)))
    else:
        remaining = 0
        estimate_days = 0

    await update.message.reply_text(
        f"Сегодня:\n"
        f"Потреблено калорий: {consumed:.0f} kcal\n"
        f"Сожжено: {burned:.0f} kcal\n"
        f"Баланс: {net:.0f} kcal\n"
        f"Прогноз: примерно {estimate_days} дней до цели (приближённо)."
    )

# ====== Сообщения/ошибки ======
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /start, /set_profile и т.д.")

# ====== Глобальная настройка и запуск ======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_profile", set_profile))
    app.add_handler(CommandHandler("set_notifications", set_notifications))
    app.add_handler(CommandHandler("plan_today", plan_today))
    app.add_handler(CommandHandler("log_meal", log_meal))
    app.add_handler(CommandHandler("log_workout", log_workout))
    app.add_handler(CommandHandler("progress", progress))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    # Планирование ежедневных уведомлений можно реализовать через JobQueue
    # Пример: запускать уведомление в заданное время (реально реализуется позже)

if __name__ == "__main__":
    main()