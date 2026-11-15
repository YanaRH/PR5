from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Habit
from .tasks import send_habit_reminders

User = get_user_model()


class BaseAPITestCase(TestCase):
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

    def test_profile_update(self):
        user = User.objects.create_user(email='p2@b.com', password='StrongPass2026!')
        self.client.force_authenticate(user=user)
        response = self.client.patch('/api/users/me/', {
            'telegram_chat_id': '123456',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.telegram_chat_id, '123456')


class HabitAPITestCase(BaseAPITestCase):
    def _payload(self, **overrides):
        data = {
            'place': 'Дом', 'time': '10:00:00', 'action': 'Читать',
            'periodicity': 1, 'time_to_complete': 60,
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

    def test_pagination_limit_offset(self):
        for i in range(7):
            Habit.objects.create(user=self.user, **self._payload(action=f'Действие {i}'))
        response = self.client.get('/api/habits/?limit=5&offset=0')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 7)
        self.assertEqual(len(response.data['results']), 5)
        self.assertIsNotNone(response.data['next'])

    def test_public_habits(self):
        Habit.objects.create(user=self.user, **self._payload(is_public=True))
        Habit.objects.create(user=self.other_user, **self._payload(is_public=True))
        response = self.client.get('/api/habits/public/')
        self.assertEqual(response.data['count'], 2)


class ValidatorsTestCase(BaseAPITestCase):
    def _payload(self, **overrides):
        data = {
            'place': 'Дом', 'time': '10:00:00', 'action': 'Читать',
            'periodicity': 1, 'time_to_complete': 60,
        }
        data.update(overrides)
        return data

    def test_time_limit_exceeded(self):
        response = self.client.post('/api/habits/', self._payload(time_to_complete=200), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_periodicity_out_of_range(self):
        response = self.client.post('/api/habits/', self._payload(periodicity=8), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reward_and_related_habit_conflict(self):
        pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Ванна',
            is_pleasant=True, periodicity=1, time_to_complete=30,
        )
        response = self.client.post('/api/habits/', self._payload(
            reward='Десерт', related_habit=pleasant.pk,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_related_habit_must_be_pleasant(self):
        not_pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Зарядка',
            is_pleasant=False, periodicity=1, time_to_complete=30,
        )
        response = self.client.post('/api/habits/', self._payload(
            related_habit=not_pleasant.pk,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pleasant_habit_cannot_have_reward(self):
        response = self.client.post('/api/habits/', self._payload(
            is_pleasant=True, reward='Торт',
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pleasant_habit_cannot_have_related(self):
        pleasant = Habit.objects.create(
            user=self.user, place='Дом', time='09:00:00', action='Ванна',
            is_pleasant=True, periodicity=1, time_to_complete=30,
        )
        response = self.client.post('/api/habits/', self._payload(
            is_pleasant=True, related_habit=pleasant.pk,
        ), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CeleryTasksTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='tg@example.com', password='StrongPass2026!',
            telegram_chat_id='123456',
        )

    @patch('habits.tasks.requests.post')
    def test_send_reminders(self, mock_post):
        from django.utils import timezone
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user, place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать', periodicity=1, time_to_complete=60,
        )
        result = send_habit_reminders()
        self.assertIn('Processed', result)
        mock_post.assert_called()

    @patch('habits.tasks.requests.post', side_effect=Exception('fail'))
    def test_send_reminders_handles_error(self, mock_post):
        from django.utils import timezone
        now = timezone.localtime()
        Habit.objects.create(
            user=self.user, place='Дом',
            time=now.time().replace(second=0, microsecond=0),
            action='Читать', periodicity=1, time_to_complete=60,
        )
        # не должно падать
        send_habit_reminders()
