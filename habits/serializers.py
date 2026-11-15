from rest_framework import serializers

from .models import Habit


class HabitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = (
            'id', 'user', 'place', 'time', 'action',
            'is_pleasant', 'related_habit', 'periodicity',
            'reward', 'time_to_complete', 'is_public',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'user', 'created_at', 'updated_at')

    def validate(self, attrs):
        # Дополнительная проверка на уровне сериализатора
        instance = Habit(**attrs)
        instance.clean()
        return attrs
