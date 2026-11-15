import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BASE = f"https://api.telegram.org/bot{TOKEN}"

# Шаг 1: получаем обновления
print("→ Запрашиваю getUpdates...")
try:
    r = requests.get(f"{BASE}/getUpdates", timeout=15)
except Exception as e:
    print(f"❌ СЕТЬ: {type(e).__name__}: {e}")
    print("   Скорее всего, не включён VPN. Включи и запусти снова.")
    exit(1)

data = r.json()
if not data.get('ok'):
    print(f"❌ Telegram вернул ошибку: {data}")
    exit(1)

if not data.get('result'):
    print("⚠️  Нет сообщений от бота.")
    print("   Открой Telegram → найди своего бота → напиши /start → запусти скрипт снова.")
    exit(0)

# Шаг 2: берём chat_id из последнего сообщения
chat_id = data['result'][-1]['message']['chat']['id']
print(f"✅ Найден chat_id: {chat_id}")

# Шаг 3: отправляем тестовое сообщение
print(f"→ Отправляю тестовое сообщение на chat_id={chat_id}...")
r = requests.post(
    f"{BASE}/sendMessage",
    data={'chat_id': chat_id, 'text': '✅ Тест из терминала прошёл!'},
    timeout=15,
)
print(f"Ответ: {r.json()}")

if r.json().get('ok'):
    print("\n🎉 Проверь Telegram — сообщение должно прийти.")
else:
    print("\n❌ Не отправилось. Смотри текст ошибки выше.")