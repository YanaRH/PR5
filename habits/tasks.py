import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Habit


@shared_task
def send_habit_reminders():
    """Отправляет напоминания в Telegram по привычкам на текущую минуту."""
    now = timezone.localtime()
    current_time = now.time().replace(second=0, microsecond=0)

    habits = Habit.objects.filter(
        user__telegram_chat_id__isnull=False,
        time__hour=current_time.hour,
        time__minute=current_time.minute,
    ).exclude(user__telegram_chat_id='')

    sent = 0
    for habit in habits:
        text = (
            f'⏰ Напоминание!\n'
            f'Действие: {habit.action}\n'
            f'Место: {habit.place}\n'
            f'Время: {habit.time.strftime("%H:%M")}'
        )
        try:
            requests.post(
                f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage',
                data={
                    'chat_id': habit.user.telegram_chat_id,
                    'text': text,
                },
                timeout=10,
            )
            sent += 1
        except Exception:
            # один сбой не должен валить всю рассылку
            pass

    return f'Processed {habits.count()} habits, sent {sent}'
