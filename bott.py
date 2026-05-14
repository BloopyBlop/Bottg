import os
import json
from datetime import datetime, date
from typing import Optional, Dict, Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ====== Настройки ======
BOT_TOKEN = "8414719305:AAHnGkDNUfVqo0MHgLORR9gi_50GYutqgrM"
DATA_FILE = "fitness_users.json"

# ====== Модели ======
class UserProfile:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.name: Optional[str] = None
        self.gender: Optional[str] = None
        self.age: Optional[int] = None
        self.height_cm: Optional[float] = None
        self.weight_kg: Optional[float] = None
        self.calories_per_day: Optional[float] = None
        self.imt: Optional[float] = None
        self.tdee: Optional[float] = None
        self.goal: Optional[str] = None
        self.notification_time: Optional[str] = None
        self.log: Dict[str, Any] = {
            "meals": [],
            "workouts": [],
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

# ====== Функции ======
def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100.0
    if height_m <= 0:
        return 0.0
    return weight_kg / (height_m * height_m)

def mh_food_calorie_needs(gender: str, age: int, height_cm: float, weight_kg: float) -> float:
    if gender.lower() in ["male", "m"]:
        s = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        s = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    return max(1000, s)

def estimate_tdee(bmr: float, activity_factor: float = 1.35) -> float:
    return bmr * activity_factor

# ====== Команды ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_users()
    uid = user.id
    if uid not in users:
        users[uid] = UserProfile(uid)
    save_users(users)

    await update.message.reply_text(
        "🤖 Привет! Я фитнес-помощник\n\n"
        "Команды:\n"
        "/set_profile рост вес возраст пол\n"
        "Пример: /set_profile 175 70 25 male\n\n"
        "/plan_today - план на сегодня\n"
        "/log_meal название калории - записать еду\n"
        "/log_workout название калории - тренировку\n"
        "/progress - статистика\n"
        "/set_notifications 09:00 - уведомления"
    )

async def set_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    users = load_users()
    uid = update.effective_user.id
    if uid not in users:
        users[uid] = UserProfile(uid)

    u = users[uid]

    if len(args) >= 4:
        try:
            u.height_cm = float(args[0])
            u.weight_kg = float(args[1])
            u.age = int(args[2])
            gender = args[3].lower()
            u.gender = "male" if gender in ["male", "m"] else "female"
            
            u.imt = calculate_bmi(u.weight_kg, u.height_cm)
            bmr = mh_food_calorie_needs(u.gender, u.age, u.height_cm, u.weight_kg)
            u.tdee = estimate_tdee(bmr, 1.4)
            
            save_users(users)
            await update.message.reply_text(
                f"✅ Профиль сохранён!\n"
                f"BMI: {u.imt:.1f}\n"
                f"Норма калорий: {u.tdee:.0f} ккал/день"
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    else:
        await update.message.reply_text("Пример: /set_profile 175 70 25 male")

async def plan_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users = load_users()
    u = users.get(uid)
    
    if not u or not u.tdee:
        await update.message.reply_text("Сначала настройте профиль: /set_profile")
        return
    
    await update.message.reply_text(
        f"📅 Ваш план на сегодня:\n"
        f"🍽️ Рекомендуется: {u.tdee:.0f} ккал\n"
        f"💪 Рекомендация: 30 минут кардио\n"
        f"🥤 Пейте воду 2 литра"
    )

async def log_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Пример: /log_meal пицца 500")
        return
    
    name = " ".join(args[:-1])
    try:
        kcal = float(args[-1])
    except:
        await update.message.reply_text("Калории должны быть числом")
        return
    
    users = load_users()
    uid = update.effective_user.id
    u = users.get(uid)
    
    if not u:
        await update.message.reply_text("Сначала /start")
        return
    
    entry = {"name": name, "kcal": kcal, "time": datetime.now().strftime("%H:%M")}
    u.log.setdefault("meals", []).append(entry)
    save_users(users)
    
    await update.message.reply_text(f"🍔 Записано: {name} - {kcal} ккал")

async def log_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Пример: /log_workout бег 300")
        return
    
    name = " ".join(args[:-1])
    try:
        kcal = float(args[-1])
    except:
        kcal = 0
    
    users = load_users()
    uid = update.effective_user.id
    u = users.get(uid)
    
    if not u:
        await update.message.reply_text("Сначала /start")
        return
    
    entry = {"name": name, "calories_burned": kcal, "time": datetime.now().strftime("%H:%M")}
    u.log.setdefault("workouts", []).append(entry)
    save_users(users)
    
    await update.message.reply_text(f"💪 Записано: {name} - сожжено {kcal} ккал")

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users = load_users()
    u = users.get(uid)
    
    if not u:
        await update.message.reply_text("Сначала /start")
        return
    
    consumed = sum(item.get("kcal", 0) for item in u.log.get("meals", []))
    burned = sum(item.get("calories_burned", 0) for item in u.log.get("workouts", []))
    
    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"🍽️ Съедено: {consumed:.0f} ккал\n"
        f"🔥 Сожжено: {burned:.0f} ккал\n"
        f"⚖️ Баланс: {consumed - burned:.0f} ккал"
    )

async def set_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /set_notifications 09:00")
        return
    
    time_str = context.args[0]
    users = load_users()
    uid = update.effective_user.id
    
    if uid not in users:
        users[uid] = UserProfile(uid)
    
    users[uid].notification_time = time_str
    save_users(users)
    await update.message.reply_text(f"🔔 Уведомления в {time_str}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /start")

# ====== Запуск ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_profile", set_profile))
    app.add_handler(CommandHandler("plan_today", plan_today))
    app.add_handler(CommandHandler("log_meal", log_meal))
    app.add_handler(CommandHandler("log_workout", log_workout))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("set_notifications", set_notifications))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()