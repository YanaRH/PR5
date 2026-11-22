import logging
from urllib.parse import quote

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Habit

logger = logging.getLogger(__name__)


def _send_telegram(chat_id, text):
    """Пытается отправить сообщение напрямую, при блокировке — через прокси."""
    token = settings.TELEGRAM_BOT_TOKEN

    # Попытка 1: напрямую (работает с VPN)
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': text},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get('ok'):
            return True, 'direct'
        logger.warning(
            'Telegram direct returned %s: %s',
            r.status_code, r.text[:200],
        )
    except Exception as exc:
        logger.info('Direct Telegram failed: %s', exc)

    # Попытка 2: через публичный CORS-прокси (работает без VPN)
    try:
        inner_url = (
            f'https://api.telegram.org/bot{token}/sendMessage'
            f'?chat_id={chat_id}&text={quote(text)}'
        )
        proxy_url = f'https://api.allorigins.win/raw?url={quote(inner_url, safe="")}'
        r = requests.get(proxy_url, timeout=15)
        if r.status_code == 200:
            try:
                if r.json().get('ok'):
                    return True, 'proxy'
            except ValueError:
                pass
            logger.warning(
                'Telegram proxy returned %s: %s',
                r.status_code, r.text[:200],
            )
        return False, f'proxy returned {r.status_code}'
    except Exception as exc:
        logger.error('Proxy Telegram failed: %s', exc)
        return False, str(exc)


@shared_task
def send_habit_reminders():
    """Отправляет напоминания по привычкам с учётом времени и периодичности."""
    now = timezone.localtime()
    current_time = now.time().replace(second=0, microsecond=0)
    today = now.date()

    habits = Habit.objects.filter(
        user__telegram_chat_id__isnull=False,
        time__hour=current_time.hour,
        time__minute=current_time.minute,
    ).exclude(user__telegram_chat_id='')

    sent = 0
    for habit in habits:
        # --- Проверка периодичности ---
        if habit.last_reminder_sent:
            days_since = (today - habit.last_reminder_sent).days
            if days_since < habit.periodicity:
                logger.debug(
                    'Skip habit %s: periodicity=%s, days_since=%s',
                    habit.pk, habit.periodicity, days_since,
                )
                continue

        text = (
            f'⏰ Напоминание!\n'
            f'Действие: {habit.action}\n'
            f'Место: {habit.place}\n'
            f'Время: {habit.time.strftime("%H:%M")}'
        )
        ok, info = _send_telegram(habit.user.telegram_chat_id, text)
        if ok:
            sent += 1
            habit.last_reminder_sent = today
            habit.save(update_fields=['last_reminder_sent'])
            logger.info('Sent habit %s via %s', habit.pk, info)
        else:
            logger.warning('Failed habit %s: %s', habit.pk, info)

    return f'Processed {habits.count()} habits, sent {sent}'