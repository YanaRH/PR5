from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .validators import validate_periodicity, validate_time_limit


class Habit(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='habits', verbose_name='Пользователь',
    )
    place = models.CharField(max_length=255, verbose_name='Место')
    time = models.TimeField(verbose_name='Время')
    action = models.CharField(max_length=500, verbose_name='Действие')
    is_pleasant = models.BooleanField(default=False, verbose_name='Приятная привычка')
    related_habit = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='related_to', verbose_name='Связанная привычка',
    )
    periodicity = models.PositiveSmallIntegerField(
        default=1, validators=[validate_periodicity],
        verbose_name='Периодичность (дни)',
    )
    reward = models.CharField(
        max_length=500, blank=True, verbose_name='Вознаграждение',
    )
    time_to_complete = models.PositiveIntegerField(
        validators=[validate_time_limit],
        verbose_name='Время на выполнение (сек)',
    )
    last_reminder_sent = models.DateField(
        null=True, blank=True,
        verbose_name='Дата последнего напоминания',
    )
    is_public = models.BooleanField(default=False, verbose_name='Публичная')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Привычка'
        verbose_name_plural = 'Привычки'
        ordering = ['-created_at']

    def clean(self):
        errors = {}

        if self.reward and self.related_habit:
            errors['reward'] = 'Нельзя одновременно указывать вознаграждение и связанную привычку.'

        if self.related_habit and not self.related_habit.is_pleasant:
            errors['related_habit'] = 'Связанная привычка должна быть приятной.'

        if self.is_pleasant:
            if self.reward:
                errors['reward'] = 'У приятной привычки не может быть вознаграждения.'
            if self.related_habit:
                errors['related_habit'] = 'У приятной привычки не может быть связанной привычки.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.action} в {self.time} в {self.place}'
