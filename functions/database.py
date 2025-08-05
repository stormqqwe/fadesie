import os
import dns.resolver
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import datetime

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGODB_DB") or os.getenv("MONGO_DB")

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]
loverooms_collection = db["loverooms"]

# Доступные сердечки для выбора
AVAILABLE_HEARTS = ["💖", "❤️", "💙", "🧡", "💚", "💛", "💜", "🖤", "💗", "💓", "💔", "💟", "💕", "💘"]
DEFAULT_HEART = "💖"

async def register_marriage(server_id, user_id, partner_id):
    # Проверяем, нет ли уже существующей записи для этих пользователей
    existing = await loverooms_collection.find_one({
        "server_id": server_id,
        "couple": {
            "$elemMatch": {
                "user_id": {"$in": [user_id, partner_id]}
            }
        }
    })
    
    if existing:
        return False
    
    # Создаем новую запись в loverooms
    await loverooms_collection.insert_one({
        "server_id": server_id,
        "channel_id": None,  # Канал будет добавлен позже при создании комнаты
        "couple": [
            {"user_id": user_id},
            {"user_id": partner_id}
        ],
        "quote": "",
        "registration": datetime.datetime.utcnow(),
        "together": 0,
        "banner": "https://i.ibb.co/tT0dYWXj/4c2398e6be397bb08b5cb70b2192d730.gif",
        "heart": DEFAULT_HEART  # Добавляем сердечко по умолчанию
    })
    return True

async def get_marriage_status(server_id, user_id):
    marriage = await loverooms_collection.find_one({
        "server_id": server_id,
        "couple": {
            "$elemMatch": {
                "user_id": user_id
            }
        }
    })
    
    if marriage:
        # Находим ID партнера (тот, который не равен user_id)
        for couple_member in marriage["couple"]:
            if couple_member["user_id"] != user_id:
                return couple_member["user_id"]
    
    return None

async def register_loveroom(server_id, channel_id, user_id, partner_id):
    # Проверяем, есть ли уже запись о браке
    marriage = await loverooms_collection.find_one({
        "server_id": server_id,
        "couple": {
            "$elemMatch": {
                "user_id": {"$in": [user_id, partner_id]}
            }
        }
    })
    
    if marriage:
        # Обновляем существующую запись, добавляя channel_id
        await loverooms_collection.update_one(
            {"_id": marriage["_id"]},
            {"$set": {"channel_id": channel_id}}
        )
        return True
    else:
        # Создаем новую запись
        await loverooms_collection.insert_one({
            "server_id": server_id,
            "channel_id": channel_id,
            "couple": [
                {"user_id": user_id},
                {"user_id": partner_id}
            ],
            "quote": "",
            "registration": datetime.datetime.utcnow(),
            "together": 0,
            "banner": "",
            "heart": DEFAULT_HEART  # Добавляем сердечко по умолчанию
        })
        return True

async def get_loveroom_by_user(server_id, user_id):
    loveroom = await loverooms_collection.find_one({
        "server_id": server_id,
        "couple": {
            "$elemMatch": {
                "user_id": user_id
            }
        }
    })
    return loveroom

async def delete_loveroom(server_id, channel_id):
    # Удаляем только канал, но сохраняем запись о браке
    result = await loverooms_collection.update_one(
        {"server_id": server_id, "channel_id": channel_id},
        {"$set": {"channel_id": None}}
    )
    return result.modified_count > 0

async def get_love_profile(server_id, user_id):
    """Получить данные любовного профиля для пользователя"""
    loveroom = await get_loveroom_by_user(server_id, user_id)
    if not loveroom:
        return None
    
    # Находим ID партнера (тот, который не равен user_id)
    partner_id = None
    for couple_member in loveroom["couple"]:
        if couple_member["user_id"] != user_id:
            partner_id = couple_member["user_id"]
            break
    
    # Форматируем дату регистрации
    registration_date = loveroom["registration"]
    
    # Получаем данные о времени из базы данных
    together_time_minutes = loveroom.get("together", 0)
    
    # Рассчитываем общее время со дня регистрации в днях
    days_since_registration = (datetime.datetime.utcnow() - registration_date).days
    total_days = max(days_since_registration, 1)  # Минимум 1 день
    
    # Конвертируем время вместе в часы, минуты, секунды
    together_hours = int(together_time_minutes // 60)
    together_minutes = int(together_time_minutes % 60)
    together_seconds = int((together_time_minutes * 60) % 60)  # Секунды из дробной части минут
    
    # Получаем выбранное сердечко или используем значение по умолчанию
    heart = loveroom.get("heart", DEFAULT_HEART)
    
    return {
        "partner_id": partner_id,
        "registration_date": registration_date.strftime("%d.%m.%Y"),
        "quote": loveroom.get("quote", ""),
        "banner": loveroom.get("banner", ""),
        "channel_id": loveroom.get("channel_id"),
        "together": {
            "hours": together_hours,
            "minutes": together_minutes,
            "seconds": together_seconds
        },
        "days_since_registration": total_days,
        "heart": heart
    }

async def update_loveroom_time(server_id, channel_id, total_time_minutes, together_time_minutes):
    """Update time spent in loveroom"""
    # Ensure the values are positive numbers
    together_time_minutes = max(0, together_time_minutes)
    
    # Round to 2 decimal places to avoid floating point issues
    together_time_minutes = round(together_time_minutes, 2)
    
    # Update the database
    result = await loverooms_collection.update_one(
        {"server_id": server_id, "channel_id": channel_id},
        {"$inc": {"together": together_time_minutes}}
    )
    
    return result.modified_count > 0

async def update_loveroom_quote(server_id, channel_id, quote):
    result = await loverooms_collection.update_one(
        {"server_id": server_id, "channel_id": channel_id},
        {"$set": {"quote": quote}}
    )
    return result.modified_count > 0

async def update_loveroom_banner(server_id, channel_id, banner_url):
    result = await loverooms_collection.update_one(
        {"server_id": server_id, "channel_id": channel_id},
        {"$set": {"banner": banner_url}}
    )
    return result.modified_count > 0

async def update_loveroom_heart(server_id, channel_id, heart):
    """Update the heart symbol for a loveroom"""
    # Validate heart symbol
    if heart not in AVAILABLE_HEARTS:
        heart = DEFAULT_HEART
        
    result = await loverooms_collection.update_one(
        {"server_id": server_id, "channel_id": channel_id},
        {"$set": {"heart": heart}}
    )
    return result.modified_count > 0

async def delete_marriage(server_id, user_id, partner_id):
    """Delete a marriage record from the database"""
    # Delete the marriage record from loverooms collection
    result = await loverooms_collection.delete_one({
        "server_id": server_id,
        "couple": {
            "$all": [
                {"$elemMatch": {"user_id": user_id}},
                {"$elemMatch": {"user_id": partner_id}}
            ]
        }
    })
    return result.deleted_count > 0
