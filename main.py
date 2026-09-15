import asyncio
import json
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo
from threading import Thread

import aiohttp
from flask import Flask
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.exceptions import TelegramForbiddenError

# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8858398474:AAFe_a7bEk-sVU40T7Bcut0WzVGZqQY7GsE")

AUTO_SEND_HOUR = 8
AUTO_SEND_MINUTE = 0

TIMEZONE = ZoneInfo("Asia/Tashkent")

USERS_FILE = "users.json"

# =========================================================
# FLASK SERVER (Render uchun)
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 Ob-havo boti ishlamoqda!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================================================
# VILOYATLAR
# =========================================================

REGIONS = {
    "tashkent": ("Toshkent shahri", 41.3111, 69.2797),
    "andijan": ("Andijon", 40.7821, 72.3442),
    "bukhara": ("Buxoro", 39.7747, 64.4286),
    "fergana": ("Farg‘ona", 40.3842, 71.7842),
    "jizzakh": ("Jizzax", 40.1158, 67.8422),
    "namangan": ("Namangan", 40.9983, 71.6726),
    "navoi": ("Navoiy", 40.0844, 65.3792),
    "qashqadarya": ("Qashqadaryo", 38.8606, 65.7891),
    "samarkand": ("Samarqand", 39.6542, 66.9597),
    "sirdarya": ("Sirdaryo", 40.4897, 68.7842),
    "surkhandarya": ("Surxondaryo", 37.2242, 67.2783),
    "tashkent_region": ("Toshkent viloyati", 41.2709, 69.2642),
    "khorezm": ("Xorazm", 41.5566, 60.6275),
    "karakalpakstan": ("Qoraqalpog‘iston", 42.4647, 59.6003),
}

REGION_KEYS = list(REGIONS.keys())

# =========================================================
# OB-HAVO KODLARI
# =========================================================

WEATHER_CODES = {
    0: "☀️ Ochiq havo",
    1: "🌤 Asosan ochiq",
    2: "⛅ Qisman bulutli",
    3: "☁️ Bulutli",

    45: "🌫 Tuman",
    48: "🌫 Qirovli tuman",

    51: "🌦 Yengil yomg‘ir",
    53: "🌦 Yomg‘ir",
    55: "🌧 Kuchli yomg‘ir",

    56: "🌧 Muzlagan yomg‘ir",
    57: "🌧 Muzlagan yomg‘ir",

    61: "🌧 Yengil yomg‘ir",
    63: "🌧 Yomg‘ir",
    65: "🌧 Kuchli yomg‘ir",

    66: "🌨 Muzlagan yomg‘ir",
    67: "🌨 Kuchli muzlagan yomg‘ir",

    71: "🌨 Yengil qor",
    73: "❄️ Qor",
    75: "❄️ Kuchli qor",
    77: "❄️ Qor donachalari",

    80: "🌦 Yengil yomg‘ir yog‘ishi",
    81: "🌧 Yomg‘ir yog‘ishi",
    82: "🌧 Kuchli yomg‘ir yog‘ishi",

    85: "🌨 Qor yog‘ishi",
    86: "❄️ Kuchli qor yog‘ishi",

    95: "⛈ Momaqaldiroq",
    96: "⛈ Do‘l bilan momaqaldiroq",
    99: "⛈ Kuchli momaqaldiroq",
}


# =========================================================
# FOYDALANUVCHILARNI SAQLASH
# =========================================================

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=4)


users = load_users()

# =========================================================
# BOT
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =========================================================
# ASOSIY MENYU
# =========================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🌤 Ob-havo"),
            KeyboardButton(text="📅 7 kunlik")
        ],
        [
            KeyboardButton(
                text="📍 Mening joylashuvim",
                request_location=True
            )
        ],
        [
            KeyboardButton(text="🔔 Avtomatik yuborish"),
            KeyboardButton(text="🔕 O‘chirish")
        ],
        [
            KeyboardButton(text="ℹ️ Bot haqida")
        ]
    ],
    resize_keyboard=True
)


# =========================================================
# VILOYATLAR MENYUSI
# =========================================================

def regions_keyboard(action: str = "current"):
    buttons = []
    for key, value in REGIONS.items():
        name = value[0]
        buttons.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"region:{action}:{key}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =========================================================
# "KEYINGI VILOYAT OB-HAVOSI" TUGMASI
# =========================================================

def next_region_button(action: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➡️ Keyingi viloyat ob-havosi",
                    callback_data=f"show_regions:{action}"
                )
            ]
        ]
    )


# =========================================================
# API DAN OB-HAVO OLISH
# =========================================================

async def get_weather(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "surface_pressure,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min"
        ),
        "forecast_days": 7,
        "timezone": "Asia/Tashkent"
    }
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                return await response.json()
    except Exception as e:
        print(f"Ob-havo olishda xatolik: {e}")
        return None

        return await response.json()


# =========================================================
# FAQAT BUGUNGI OB-HAVO
# =========================================================

async def make_current_weather_text(latitude, longitude, location_name):
    data = await get_weather(latitude, longitude)
    if not data:
        return "⚠️ Ob-havo serverida xatolik yuz berdi."

    current = data["current"]
    temperature = current["temperature_2m"]
    humidity = current["relative_humidity_2m"]
    pressure = current["surface_pressure"]
    wind = current["wind_speed_10m"]
    code = current["weather_code"]

    condition = WEATHER_CODES.get(code, "🌤 Noma'lum ob-havo")
    pressure_mmhg = round(pressure * 0.750062)

    text = (
        f"📍 <b>{location_name}</b>\n\n"
        f"🌤 <b>Hozirgi ob-havo:</b>\n"
        f"{condition}\n\n"
        f"🌡 Harorat: <b>{temperature}°C</b>\n"
        f"💧 Namlik: <b>{humidity}%</b>\n"
        f"💨 Shamol: <b>{wind} km/soat</b>\n"
        f"🧭 Bosim: <b>{pressure_mmhg} mm sim. ust.</b>"
    )
    return text


# =========================================================
# 7 KUNLIK OB-HAVO
# =========================================================

async def make_weather_text(latitude, longitude, location_name):
    data = await get_weather(latitude, longitude)
    if not data:
        return "⚠️ Ob-havo serverida xatolik yuz berdi."

    daily = data["daily"]
    daily_dates = daily["time"]
    daily_codes = daily["weather_code"]
    daily_max = daily["temperature_2m_max"]
    daily_min = daily["temperature_2m_min"]

    text = (
        f"📍 <b>{location_name}</b>\n\n"
        f"📅 <b>7 kunlik ob-havo:</b>\n"
    )

    days_uz = [
        "Dushanba", "Seshanba", "Chorshanba",
        "Payshanba", "Juma", "Shanba", "Yakshanba"
    ]

    for i in range(7):
        current_date = date.fromisoformat(daily_dates[i])
        if i == 0:
            day_name = "Bugun"
        elif i == 1:
            day_name = "Ertaga"
        else:
            day_name = days_uz[current_date.weekday()]

        weather = WEATHER_CODES.get(daily_codes[i], "🌤 Noma'lum")
        maximum = daily_max[i]
        minimum = daily_min[i]

        text += (
            f"\n<b>{day_name}</b> ({current_date.strftime('%d.%m')})\n"
            f"{weather}\n"
            f"🌡 {minimum}°C — {maximum}°C\n"
        )

    return text


# =========================================================
# /START KOMANDASI
# =========================================================

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in users:
        users[user_id] = {
            "latitude": 41.3111,
            "longitude": 69.2797,
            "location_name": "Toshkent shahri",
            "auto": False,
            "last_sent": ""
        }
        save_users()

    await message.answer(
        "🌤 <b>Ob-havo botiga xush kelibsiz!</b>\n\n"
        "Men sizga:\n"
        "🌡 Hozirgi ob-havoni\n"
        "📅 7 kunlik prognozni\n"
        "📍 Joylashuvingiz bo‘yicha ob-havoni\n"
        "🔔 Har kuni avtomatik ob-havoni yuboraman.\n\n"
        "Kerakli bo‘limni tanlang:",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


# =========================================================
# OB-HAVO (Bugungi uchun hudud tanlash)
# =========================================================

@dp.message(F.text == "🌤 Ob-havo")
async def weather_menu(message: types.Message):
    await message.answer(
        "🏙 <b>Hududingizni tanlang:</b>",
        reply_markup=regions_keyboard(action="current"),
        parse_mode="HTML"
    )


# =========================================================
# 7 KUNLIK HUDUD TANLASH
# =========================================================

@dp.message(F.text == "📅 7 kunlik")
async def seven_days_menu(message: types.Message):
    await message.answer(
        "🏙 <b>7 kunlik ob-havo uchun hududni tanlang:</b>",
        reply_markup=regions_keyboard(action="seven"),
        parse_mode="HTML"
    )


# =========================================================
# "KEYINGI VILOYAT OB-HAVOSI" BOSILGANDA VILOYATLARNI CHIQARISH
# =========================================================

@dp.callback_query(F.data.startswith("show_regions:"))
async def show_regions_callback(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]  # "current" yoki "seven"

    title = "🏙 <b>7 kunlik ob-havo uchun hududni tanlang:</b>" if action == "seven" else "🏙 <b>Hududingizni tanlang:</b>"

    await callback.message.answer(
        title,
        reply_markup=regions_keyboard(action=action),
        parse_mode="HTML"
    )
    await callback.answer()


# =========================================================
# VILOYAT TANLANGANDA OB-HAVONI CHIQARISH
# =========================================================

@dp.callback_query(F.data.startswith("region:"))
async def choose_region(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]  # "current" yoki "seven"
    region_key = parts[2]  # viloyat kaliti

    name, latitude, longitude = REGIONS[region_key]
    user_id = str(callback.from_user.id)

    users[user_id] = {
        "latitude": latitude,
        "longitude": longitude,
        "location_name": name,
        "auto": users.get(user_id, {}).get("auto", False),
        "last_sent": users.get(user_id, {}).get("last_sent", "")
    }
    save_users()

    await callback.answer(f"{name} tanlandi!")
    await callback.message.answer("⏳ Ob-havo olinmoqda...")

    if action == "seven":
        text = await make_weather_text(latitude, longitude, name)
    else:
        text = await make_current_weather_text(latitude, longitude, name)

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=next_region_button(action=action)
    )


# =========================================================
# JOYLASHUVNI QABUL QILISH
# =========================================================

@dp.message(F.location)
async def receive_location(message: types.Message):
    latitude = message.location.latitude
    longitude = message.location.longitude
    user_id = str(message.from_user.id)

    users[user_id] = {
        "latitude": latitude,
        "longitude": longitude,
        "location_name": "Sizning joylashuvingiz",
        "auto": users.get(user_id, {}).get("auto", False),
        "last_sent": users.get(user_id, {}).get("last_sent", "")
    }
    save_users()

    await message.answer("📍 Joylashuvingiz qabul qilindi!\n⏳ Ob-havo olinmoqda...")
    text = await make_current_weather_text(latitude, longitude, "Sizning joylashuvingiz")

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=next_region_button(action="current")
    )


# =========================================================
# AVTOMATIK YUBORISH / O'CHIRISH VA BOT HAQIDA
# =========================================================

@dp.message(F.text == "🔔 Avtomatik yuborish")
async def enable_auto(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in users:
        users[user_id] = {
            "latitude": 41.3111,
            "longitude": 69.2797,
            "location_name": "Toshkent shahri",
            "auto": True,
            "last_sent": ""
        }
    else:
        users[user_id]["auto"] = True
    save_users()

    await message.answer(
        "🔔 <b>Avtomatik yuborish yoqildi!</b>\n\n"
        "Har kuni soat <b>08:00</b> da ob-havo yuboriladi. 🌤",
        parse_mode="HTML"
    )


@dp.message(F.text == "🔕 O‘chirish")
async def disable_auto(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in users:
        users[user_id]["auto"] = False
        save_users()
    await message.answer("🔕 Avtomatik ob-havo yuborish o‘chirildi.")


@dp.message(F.text == "ℹ️ Bot haqida")
async def about_bot_message(message: types.Message):
    await message.answer(
        "ℹ️ <b>Bot haqida ma'lumot:</b>\n\n"
        "Ushbu bot O'zbekiston va boshqa hududlardagi ob-havo ma'lumotlarini tezkor va aniq taqdim etish uchun yaratilgan.\n\n"
        "<b>Bot imkoniyatlari:</b>\n"
        "🌤 <b>Ob-havo:</b> Joriy kundagi ob-havo sharoitlari (harorat, namlik, shamol va bosim) haqida ma'lumot beradi.\n"
        "📅 <b>7 kunlik:</b> Kelgusi 7 kun uchun ob-havo prognozini ko'rsatadi.\n"
        "📍 <b>Mening joylashuvim:</b> GPS orqali turgan joyingizdagi ob-havoni aniqlaydi.\n"
        "🔔 <b>Avtomatik yuborish:</b> Har kuni ertalab soat 08:00 da ob-havo ma'lumotini o'zi yuborib turadi.\n\n"
        "Botdan foydalanishda savollar yoki takliflar tug'ilsa, administratorga murojaat qilishingiz mumkin.",
        parse_mode="HTML"
    )


# =========================================================
# AVTOMATIK OB-HAVO LOOP
# =========================================================

async def auto_weather_loop():
    while True:
        try:
            now = datetime.now(TIMEZONE)
            if now.hour == AUTO_SEND_HOUR and now.minute == AUTO_SEND_MINUTE:
                today = now.strftime("%Y-%m-%d")
                for user_id, user in list(users.items()):
                    if not user.get("auto", False):
                        continue
                    if user.get("last_sent") == today:
                        continue
                    try:
                        text = await make_weather_text(
                            user["latitude"],
                            user["longitude"],
                            user["location_name"]
                        )
                        await bot.send_message(
                            chat_id=int(user_id),
                            text="🌅 <b>Ertalabki ob-havo</b>\n\n" + text,
                            parse_mode="HTML"
                        )
                        user["last_sent"] = today
                        save_users()
                    except TelegramForbiddenError:
                        user["auto"] = False
                        save_users()
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(30)


# =========================================================
# BOTNI ISHGA TUSHIRISH
# =========================================================

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN topilmadi!")
    print("🤖 Ob-havo bot ishga tushdi!")

    # Flask serverini alohida oqimda (thread) ishga tushiramiz
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Ob-havo yuborish siklini ishga tushiramiz
    asyncio.create_task(auto_weather_loop())

    # Botni ishga tushiramiz
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
