## Ограничения окружения

В регионе разработки (Россия) домен `api.telegram.org` заблокирован на уровне провайдера.
Реальная отправка сообщений в Telegram во время разработки не проводилась/

Что реализовано и проверено:
- Задача `habits.tasks.send_habit_reminders` написана и вызывается по расписанию
  через Celery Beat (видно в логах `Scheduler: Sending due task ...`).
- Celery Worker принимает задачу и выполняет её без программных ошибок
  (`Task ... succeeded`).
- HTTP-запрос формируется корректно (проверено через мок `requests.post` в тестах
  `habits/tests.py::CeleryTasksTestCase`).
- `PATCH /api/users/me/` принимает и сохраняет `telegram_chat_id`.
