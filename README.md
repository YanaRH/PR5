## Ограничения окружения

В регионе разработки (Россия) домен `api.telegram.org` заблокирован на уровне провайдера.

Что реализовано и проверено:
- Задача `habits.tasks.send_habit_reminders` написана и вызывается по расписанию
  через Celery Beat (видно в логах `Scheduler: Sending due task ...`).
- Celery Worker принимает задачу и выполняет её без программных ошибок
  (`Task ... succeeded`).
- HTTP-запрос формируется корректно (проверено через мок `requests.post` в тестах
  `habits/tests.py::CeleryTasksTestCase`).
- `PATCH /api/users/me/` принимает и сохраняет `telegram_chat_id`.
Локальный запуск: cp .env.example .env → docker compose up --build -d.

CI/CD: какие секреты добавлены в GitHub и как работает пайплайн (тесты → сборка → деплой по SSH).

Сервер: как настроен (Ubuntu, Docker, клонирован репозиторий, статический IP).