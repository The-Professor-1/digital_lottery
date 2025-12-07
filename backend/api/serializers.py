from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Game, GameCard, CalledNumber, Deposit, Transaction

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'telegram_id', 'phone_number', 'balance', 'created_at']
        read_only_fields = ['id', 'created_at']


class CalledNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalledNumber
        fields = ['id', 'number', 'letter', 'called_at']
        read_only_fields = ['id', 'called_at']


class GameCardSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = GameCard
        fields = ['id', 'game', 'user', 'card_number', 'card_layout', 'selected_numbers', 'is_winner', 'purchased_at']
        read_only_fields = ['id', 'user', 'purchased_at']


class GameSerializer(serializers.ModelSerializer):
    gamecards = GameCardSerializer(many=True, read_only=True)
    called_numbers = CalledNumberSerializer(many=True, read_only=True)
    winner = UserSerializer(read_only=True)
    total_players = serializers.IntegerField(read_only=True)
    total_derash = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_cards = serializers.SerializerMethodField()
    card_selection_timer = serializers.SerializerMethodField()
    automatic_mode_enabled = serializers.SerializerMethodField()
    
    class Meta:
        model = Game
        fields = [
            'id', 'status', 'derash_amount', 'bet_amount', 'current_call_count',
            'started_at', 'completed_at', 'winner', 'created_at', 'updated_at',
            'gamecards', 'called_numbers', 'total_players', 'total_derash', 'total_cards', 'card_selection_timer', 'automatic_mode_enabled'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_cards(self, obj):
        """Get total_cards from GameSettings"""
        from .models import GameSettings
        settings = GameSettings.get_settings()
        return settings.total_cards
    
    def get_card_selection_timer(self, obj):
        """Get card_selection_timer from GameSettings"""
        from .models import GameSettings
        settings = GameSettings.get_settings()
        return settings.card_selection_timer
    
    def get_automatic_mode_enabled(self, obj):
        """Get automatic_mode_enabled from GameSettings"""
        from .models import GameSettings
        settings = GameSettings.get_settings()
        return settings.automatic_mode_enabled


class GameCardDetailSerializer(serializers.ModelSerializer):
    game = GameSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = GameCard
        fields = ['id', 'game', 'user', 'card_number', 'card_layout', 'selected_numbers', 'is_winner', 'purchased_at', 'mode_history']
        read_only_fields = ['id', 'user', 'purchased_at']


class DepositSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Deposit
        fields = ['id', 'user', 'amount', 'bank_text', 'admin_text', 'status', 'matched_at', 'created_at']
        read_only_fields = ['id', 'user', 'admin_text', 'status', 'matched_at', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['id', 'user', 'transaction_type', 'amount', 'game', 'description', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class SelectCardSerializer(serializers.Serializer):
    card_number = serializers.IntegerField(min_value=1)  # Max value validated in view using settings


class MarkNumberSerializer(serializers.Serializer):
    number = serializers.IntegerField(min_value=1, max_value=75)


class CreateGameSerializer(serializers.Serializer):
    bet_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)


class CallNumberSerializer(serializers.Serializer):
    number = serializers.IntegerField(min_value=1, max_value=75)

