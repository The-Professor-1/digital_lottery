from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Game, GameCard, CalledNumber, Deposit, Transaction

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'telegram_id', 'phone_number', 'balance', 'unwithdrawable_balance', 'withdrawable_balance', 'first_name', 'last_name', 'created_at']
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
    called_numbers = serializers.SerializerMethodField()  # Changed to SerializerMethodField to use Redis
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
    
    def get_called_numbers(self, obj):
        """
        REDIS-FIRST: Get called numbers from Redis during active games (fast).
        Falls back to DB for completed games or if Redis unavailable.
        """
        try:
            # For active games, use Redis (fast, no DB hit)
            if obj.status == 'active':
                from .redis_utils import get_called_numbers_list_from_redis
                from .models import CalledNumber
                
                try:
                    called_numbers_list = get_called_numbers_list_from_redis(obj.id)
                    if called_numbers_list is not None and len(called_numbers_list) > 0:
                        # Convert to serializer format
                        result = []
                        for num in called_numbers_list:
                            try:
                                letter = CalledNumber.get_letter_for_number(num)
                                result.append({
                                    'number': num,
                                    'letter': letter,
                                    'called_at': None  # Not stored in Redis, but frontend doesn't need it
                                })
                            except Exception as e:
                                # Skip invalid numbers
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.warning(f"⚠️ [SERIALIZER] Game {obj.id}: Invalid number {num}: {e}")
                                continue
                        return result
                    # If Redis returns empty list or None, fall through to DB
                except Exception as e:
                    # Redis error - fall back to DB
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"⚠️ [SERIALIZER] Game {obj.id}: Redis error in get_called_numbers: {e}, falling back to DB")
            
            # For completed games, waiting games, or if Redis unavailable, use DB (for history)
            try:
                return CalledNumberSerializer(obj.called_numbers.all().order_by('called_at'), many=True).data
            except Exception as e:
                # If DB query fails, return empty list
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"❌ [SERIALIZER] Game {obj.id}: DB error in get_called_numbers: {e}")
                return []
        except Exception as e:
            # Catch-all for any unexpected errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [SERIALIZER] Game {obj.id}: Unexpected error in get_called_numbers: {e}")
            import traceback
            traceback.print_exc()
            # Return empty list to prevent 500 error
            return []
    
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

