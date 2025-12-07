from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import json


class User(AbstractUser):
    """Custom User model for Telegram users"""
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.username} ({self.telegram_id})"


class Game(models.Model):
    """Bingo Game model"""
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    derash_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bet_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    current_call_count = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_games')
    winners = models.ManyToManyField(User, blank=True, related_name='shared_wins', help_text="All winners (for split derash)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'games'
        ordering = ['-created_at']

    def __str__(self):
        return f"Game {self.id} - {self.status}"

    @property
    def total_players(self):
        return self.gamecards.count()

    def recalculate_derash(self):
        """Recalculate derash_amount from actual cards to ensure accuracy"""
        from decimal import Decimal
        # Count unique users who have cards (each user pays once per game)
        unique_users = self.gamecards.values_list('user_id', flat=True).distinct()
        player_count = len(list(unique_users))
        # Recalculate: each unique player pays bet_amount once
        self.derash_amount = Decimal(str(self.bet_amount)) * Decimal(str(player_count))
        self.save(update_fields=['derash_amount'])
        # Invalidate cache
        from django.core.cache import cache
        if cache:
            cache.delete('game:current')

    @property
    def total_derash(self):
        """Calculate total derash after percentage cut
        Formula: (total_players * bid_amount) - percentage_cut
        Note: derash_amount already stores the total collected amount
        """
        from decimal import Decimal
        # derash_amount is the total collected (sum of all bet amounts)
        # Count unique users (each user pays once per game, even if they change cards)
        unique_users = self.gamecards.values_list('user_id', flat=True).distinct()
        unique_user_count = len(list(unique_users))
        
        # Recalculate derash_amount from actual unique players to ensure accuracy
        # This fixes any discrepancies from race conditions or bugs
        expected_derash = Decimal(str(self.bet_amount)) * Decimal(str(unique_user_count))
        current_derash = self.derash_amount if self.derash_amount > 0 else Decimal('0')
        
        # If derash_amount doesn't match expected, use expected value for calculation
        # (Don't save here to avoid performance issues - will be fixed on next card operation)
        if abs(current_derash - expected_derash) > Decimal('0.01'):
            # Use expected derash for calculation
            current_derash = expected_derash
        
        if current_derash > 0:
            settings = GameSettings.get_settings()
            percentage = settings.percentage_cut
            # Calculate cut amount: percentage of total collected
            cut_amount = (current_derash * percentage) / Decimal('100')
            # Prize is total collected minus the cut
            return current_derash - cut_amount
        return Decimal('0')


class GameCard(models.Model):
    """Bingo Card model - represents a card purchased by a user for a game"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='gamecards')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamecards')
    card_number = models.IntegerField()  # Card identifier (1-90 or custom range)
    card_layout = models.JSONField(default=dict)  # 5x5 grid layout with numbers
    selected_numbers = models.JSONField(default=list)  # Numbers user has marked
    is_winner = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when bingo was claimed")
    # Track mode usage - JSON field storing timestamps when user switched modes
    mode_history = models.JSONField(default=list, help_text="List of mode changes: [{'mode': 'automatic', 'timestamp': '...'}, ...]")

    class Meta:
        db_table = 'game_cards'
        unique_together = ['game', 'user']  # One card per user per game
        indexes = [
            models.Index(fields=['game', 'user']),
            models.Index(fields=['game', 'card_number']),
        ]

    def __str__(self):
        return f"Card {self.card_number} - Game {self.game.id} - {self.user.username}"

    def mark_number(self, number):
        """Mark a number as selected on this card"""
        if number not in self.selected_numbers:
            self.selected_numbers.append(number)
            self.save(update_fields=['selected_numbers'])

    def check_win(self, called_numbers):
        """Check if this card has a winning pattern"""
        # Check if all marked numbers are in called numbers
        if not all(num in called_numbers for num in self.selected_numbers):
            return False

        # Check for winning patterns
        layout = self.card_layout
        if not layout:
            return False

        # Check horizontal lines
        for row in layout:
            if all(cell.get('marked', False) for cell in row):
                return True

        # Check vertical lines
        for col_idx in range(5):
            if all(layout[row_idx][col_idx].get('marked', False) for row_idx in range(5)):
                return True

        # Check diagonal (top-left to bottom-right)
        if all(layout[i][i].get('marked', False) for i in range(5)):
            return True

        # Check diagonal (top-right to bottom-left)
        if all(layout[i][4-i].get('marked', False) for i in range(5)):
            return True

        # Check full card
        if all(cell.get('marked', False) for row in layout for cell in row):
            return True

        return False


class CalledNumber(models.Model):
    """Numbers called during a game"""
    LETTER_CHOICES = [
        ('B', 'B (1-15)'),
        ('I', 'I (16-30)'),
        ('N', 'N (31-45)'),
        ('G', 'G (46-60)'),
        ('O', 'O (61-75)'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='called_numbers')
    number = models.IntegerField()
    letter = models.CharField(max_length=1, choices=LETTER_CHOICES)
    called_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'called_numbers'
        unique_together = ['game', 'number']  # Each number can only be called once per game
        ordering = ['called_at']
        indexes = [
            models.Index(fields=['game', 'called_at']),
        ]

    def __str__(self):
        return f"{self.letter}-{self.number}"

    @staticmethod
    def get_letter_for_number(number):
        """Get the letter (B/I/N/G/O) for a given number"""
        if 1 <= number <= 15:
            return 'B'
        elif 16 <= number <= 30:
            return 'I'
        elif 31 <= number <= 45:
            return 'N'
        elif 46 <= number <= 60:
            return 'G'
        elif 61 <= number <= 75:
            return 'O'
        return None


class Deposit(models.Model):
    """Deposit requests with manual verification"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposits')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    bank_text = models.TextField()  # Text pasted by user from bank
    admin_text = models.TextField(null=True, blank=True)  # Text pasted by admin
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deposits'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Deposit {self.id} - {self.user.username} - {self.amount} - {self.status}"

    def normalize_text(self, text):
        """Normalize text for comparison"""
        import re
        # Remove spaces, convert to lowercase, remove special characters
        text = re.sub(r'[^a-z0-9]', '', text.lower())
        return text

    def match_texts(self):
        """Check if bank_text and admin_text match"""
        if not self.admin_text:
            return False
        normalized_bank = self.normalize_text(self.bank_text)
        normalized_admin = self.normalize_text(self.admin_text)
        return normalized_bank == normalized_admin


class Transaction(models.Model):
    """Transaction history"""
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdraw', 'Withdrawal'),
        ('bet', 'Bet'),
        ('win', 'Win'),
        ('transfer', 'Transfer'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    deposit = models.ForeignKey(Deposit, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    transfer = models.ForeignKey('Transfer', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.user.username} - {self.amount}"


class GameSettings(models.Model):
    """Game configuration settings - Singleton pattern"""
    # Game timing settings
    time_between_calls = models.IntegerField(default=3, help_text="Seconds between each number call")
    card_selection_timer = models.IntegerField(default=30, help_text="Seconds for card selection window")
    
    # Game financial settings
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Default bet amount per card")
    percentage_cut = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Percentage to cut from total derash (e.g., 10.00 for 10%)")
    min_withdraw = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, help_text="Minimum withdrawal amount")
    
    # Card settings
    total_cards = models.IntegerField(default=90, help_text="Total number of cards available")
    
    # Game mode settings
    automatic_mode_enabled = models.BooleanField(default=False, help_text="If enabled, automatic mode will be available for all players")
    
    # Deposit account information (stored as JSON)
    deposit_accounts = models.JSONField(
        default=dict,
        help_text="Bank account details: {'BOA': {'name': '...', 'number': '...'}, 'CBE': {...}, 'Telebirr': {...}}"
    )
    
    # Support phone number
    support_phone = models.CharField(
        max_length=20,
        default='0952838412',
        help_text="Support phone number displayed in bot support command"
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'game_settings'
        verbose_name = 'Game Settings'
        verbose_name_plural = 'Game Settings'
    
    def __str__(self):
        return "Game Settings"
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super().save(*args, **kwargs)
        # Invalidate cache when settings are saved
        from django.core.cache import cache
        cache.delete('game_settings')
    
    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance"""
        from django.core.cache import cache
        
        # Try to get from cache first
        cache_key = 'game_settings'
        cached_settings = cache.get(cache_key)
        if cached_settings is not None:
            return cached_settings
        
        # Cache miss - fetch from database
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            # Initialize default deposit accounts
            obj.deposit_accounts = {
                'BOA': {'name': '', 'number': ''},
                'CBE': {'name': '', 'number': ''},
                'Telebirr': {'name': '', 'number': ''}
            }
            obj.save()
        
        # Cache for 60 seconds (settings don't change often)
        cache.set(cache_key, obj, 60)
        
        return obj


class DepositRequest(models.Model):
    """Enhanced deposit requests with platform and account info"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PLATFORM_CHOICES = [
        ('BOA', 'Bank of Abyssinia'),
        ('CBE', 'Commercial Bank of Ethiopia'),
        ('Telebirr', 'Telebirr'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    deposit_text = models.TextField(help_text="Text or screenshot description from user")
    photo_file_id = models.CharField(max_length=255, null=True, blank=True, help_text="Telegram file_id for screenshot")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_deposits')

    class Meta:
        db_table = 'deposit_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Deposit {self.id} - {self.user.username} - {self.amount} {self.platform} - {self.status}"


class WithdrawRequest(models.Model):
    """Withdrawal requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    PLATFORM_CHOICES = [
        ('BOA', 'Bank of Abyssinia'),
        ('CBE', 'Commercial Bank of Ethiopia'),
        ('Telebirr', 'Telebirr'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdraw_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_withdrawals')

    class Meta:
        db_table = 'withdraw_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Withdraw {self.id} - {self.user.username} - {self.amount} {self.platform} - {self.status}"


class Transfer(models.Model):
    """Transfer transactions between users"""
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfers_sent')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfers_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transfers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_user', 'created_at']),
            models.Index(fields=['to_user', 'created_at']),
        ]

    def __str__(self):
        return f"Transfer {self.id} - {self.from_user.username} → {self.to_user.username} - {self.amount}"


class AdminMessage(models.Model):
    """Admin messages to players during active games"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='admin_messages', null=True, blank=True)
    message = models.TextField()
    show_refund = models.BooleanField(default=False)
    show_cancel = models.BooleanField(default=False)
    refund_processed = models.BooleanField(default=False)
    cancel_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'admin_messages'
        ordering = ['-created_at']


class SecondAdmin(models.Model):
    """Second admin credentials for limited access dashboard"""
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)  # Will store hashed password
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'second_admin'
        ordering = ['-created_at']

    def __str__(self):
        return f"SecondAdmin: {self.username}"