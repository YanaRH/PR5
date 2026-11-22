from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Habit
from .tasks import send_habit_reminders

User = get_user_model()


class BaseAPITestCase(TestCase):
    """Базовый класс с двумя пользователями и авторизованным клиентом."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123',
        )
        self.other_user = User.objects.create_user(
            email='other@example.com', password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class AuthTestCase(TestCase):
    """Регистрация, логин, профиль."""

    def setUp(self):
        self.client = APIClient()

    def test_register(self):
        response = self.client.post('/api/users/register/', {
            'email': 'new@example.com',
            'password': 'StrongPass2026!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_login(self):
        User.objects.create_user(email='a@b.com', password='StrongPass2026!')
        response = self.client.post('/api/users/login/', {
            'email': 'a@b.com', 'password': 'StrongPass2026!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_profile(self):
        user = User.objects.create_user(email='p@b.com', password='StrongPass2026!')
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'p@b.com')

    def test_profile_update_telegram_chat_id(self):
        user = User.objects.create_user(email='p2@b.com', password='StrongPass2026!')
        self.client.force_authenticate(user=user)
        response = self.client.patch('/api/users/me/', {
            'telegram_chat_id': '123456',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.telegram_chat_id, '123456')


class HabitAPITestCase(BaseAPITestCase):
    """CRUD привычек, права доступа, пагинация, публичный список."""

    def _payload(self, **overrides):
        data = {
            'place': 'Дом',
            'time': '10:00:00',
            'action': 'Читать',
            'periodicity': 1,
            'time_to_complete': 60,
        }
        data.update(overrides)
        return data

    def test_create_habit(self):
        response = self.client.post('/api/habits/', self._payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Habit.objects.count(), 1)

    def test_unauthorized(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/habits/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_sees_only_own_habits(self):
        Habit.objects.create(user=self.user, **self._payload())
        Habit.objects.create(user=self.other_user, **self._payload())
        response = self.client.get('/api/habits/')
        self.assertEqual(response.data['count'], 1)

    def test_user_cannot_access_other_habit(self):
        other = Habit.objects.create(user=self.other_user, **self._payload())
        response = self.client.get(f'/api/habits/{other.pk}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_own_habit(self):
        habit = Habit.objects.create(user=self.user, **self._payload())
        response = self.client.patch(
            f'/api/habits/{habit.pk}/',
            {'action': 'Новое действие'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        habit.refresh_from_db()
        self.assertEqual(habit.action, 'Новое действие')

    def test_delete_own_habit(self):
        habit = Habit.objects.create(user=self.user, **self._payload())
        response = self.client.delete(f'/api/habits/{habit.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Habit.objects.filter(pk=habit.pk).exists())

    def test_pagination_limit_offset(self):
        for i in range(7):
            Habit.objects.create(
                user=self.user,
                **self._payload(action=f'Действие {i}'),
            )
        response = self.client.get('/api/habits/?limit=5&offset=0')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 7)
        self.assertEqual(len(response.data['results']), 5)
        self.assertIsNotNone(response.data['next'])

    def test_public_habits(self):
        Habit.objects.create(user=self.user, **self._payload(is_public=True))
        Habit.objects.create(user=self.other_user, **self._payload(is_public=True))
        Habit.objects.create(user=self.user, **self._payload(is_public=False))
        response = self.client.get('/api/habits/public/')
        self.assertEqual(response.data['count'], 2)


class ValidatorsTestCase(BaseAPITestCase):
    """Все 6 валидаторов из ТЗ."""

    def _payload(self, **overrides):
        data = {
            'place': 'Дом',
            'time': '10:00:00',
            'action': 'Читать',
            'periodicity': 1,
            'time_to_complete': 60,
        }
        data.update(overrides)
        return data

    def test_time_limit_exceeded(self):
        response = self.client.post(
            '/api/habits/',
            self._payload(time_to_complete=200),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_periodicity_out_of_range(self):
        response = self.client.post(
            '/api/habits/',
            self._payload(periodicity=8),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reward_and_related_habit_conflict(self):
        pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Ванна',
            is_pleasant=True, periodicity=1, time_to_complete=30,
        )
        response = self.client.post(
            '/api/habits/',
            self._payload(reward='Десерт', related_habit=pleasant.pk),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_related_habit_must_be_pleasant(self):
        not_pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Зарядка',
            is_pleasant=False, periodicity=1, time_to_complete=30,
        )
        response = self.client.post(
            '/api/habits/',
            self._payload(related_habit=not_pleasant.pk),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pleasant_habit_cannot_have_reward(self):
        response = self.client.post(
            '/api/habits/',
            self._payload(is_pleasant=True, reward='Торт'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pleasant_habit_cannot_have_related(self):
        pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Ванна',
            is_pleasant=True, periodicity=1, time_to_complete=30,
        )
        response = self.client.post(
            '/api/habits/',
            self._payload(is_pleasant=True, related_habit=pleasant.pk),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CeleryTasksTestCase(TestCase):
    """Задача send_habit_reminders: отправка, ошибки, периодичность."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='tg@example.com',
            password='StrongPass2026!',
            telegram_chat_id='123456',
        )

    def _mock_success(self, mock_post):
        """Мок успешной отправки через direct-запрос."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'ok': True}

    @patch('habits.tasks.requests.post')
    def test_send_reminders_success(self, mock_post):
        """Успешная отправка: один вызов, статус 'sent 1'."""
        self._mock_success(mock_post)
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user,
            place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать',
            periodicity=1,
            time_to_complete=60,
        )
        result = send_habit_reminders()
        self.assertIn('sent 1', result)
        mock_post.assert_called_once()
        habit = Habit.objects.first()
        self.assertEqual(habit.last_reminder_sent, now.date())

    @patch('habits.tasks.requests.get')
    @patch('habits.tasks.requests.post')
    def test_send_reminders_handles_error(self, mock_post, mock_get):
        """Direct и proxy падают — задача не падает, возвращает 'sent 0'."""
        mock_post.side_effect = Exception('direct fail')
        mock_get.side_effect = Exception('proxy fail')
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user,
            place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать',
            periodicity=1,
            time_to_complete=60,
        )
        result = send_habit_reminders()
        self.assertIn('Processed', result)
        self.assertIn('sent 0', result)
        habit = Habit.objects.first()
        self.assertIsNone(habit.last_reminder_sent)

    @patch('habits.tasks.requests.post')
    def test_periodicity_respected(self, mock_post):
        """Привычка с periodicity=7 и last_reminder_sent 3 дня назад — пропуск."""
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user,
            place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать',
            periodicity=7,
            time_to_complete=60,
            last_reminder_sent=now.date() - timedelta(days=3),
        )
        result = send_habit_reminders()
        mock_post.assert_not_called()
        self.assertIn('sent 0', result)

    @patch('habits.tasks.requests.post')
    def test_periodicity_elapsed(self, mock_post):
        """Привычка с periodicity=7 и last_reminder_sent 8 дней назад — отправка."""
        self._mock_success(mock_post)
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user,
            place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать',
            periodicity=7,
            time_to_complete=60,
            last_reminder_sent=now.date() - timedelta(days=8),
        )
        result = send_habit_reminders()
        mock_post.assert_called_once()
        self.assertIn('sent 1', result)

    @patch('habits.tasks.requests.post')
    def test_no_reminder_outside_time_window(self, mock_post):
        """Привычка с другим временем — не попадает в выборку."""
        now = timezone.localtime()
        other_time = (now + timedelta(hours=3)).time().replace(
            second=0, microsecond=0,
        )
        Habit.objects.create(
            user=self.user,
            place='Дом',
            time=other_time,
            action='Читать',
            periodicity=1,
            time_to_complete=60,
        )
        result = send_habit_reminders()
        mock_post.assert_not_called()
        self.assertIn('Processed 0', result)

    @patch('habits.tasks.requests.post')
    def test_no_reminder_without_chat_id(self, mock_post):
        """У пользователя без telegram_chat_id — ничего не отправляется."""
        user_no_tg = User.objects.create_user(
            email='nopush@example.com',
            password='StrongPass2026!',
            telegram_chat_id='',
        )
        now = timezone.localtime()
        Habit.objects.create(
            user=user_no_tg,
            place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать',
            periodicity=1,
            time_to_complete=60,
        )
        result = send_habit_reminders()
        mock_post.assert_not_called()
        self.assertIn('Processed 0', result)