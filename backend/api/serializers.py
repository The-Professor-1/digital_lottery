"""Serializers used by the lottery mini-app auth endpoints."""
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'telegram_id', 'phone_number', 'balance',
            'unwithdrawable_balance', 'withdrawable_balance',
            'first_name', 'last_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
