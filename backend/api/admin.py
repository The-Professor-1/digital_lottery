from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from .models import User, Game, GameCard, CalledNumber, Deposit, Transaction, GameSettings, DepositRequest, WithdrawRequest
from decimal import Decimal


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'telegram_id', 'phone_number', 'balance', 'is_superuser', 'is_staff', 'created_at']
    list_filter = ['created_at', 'is_active', 'is_superuser', 'is_staff']
    search_fields = ['username', 'telegram_id', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Telegram Info', {'fields': ('telegram_id', 'phone_number')}),
        ('Balance', {'fields': ('balance',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'derash_amount', 'bet_amount', 'current_call_count', 'total_players', 'winner', 'started_at', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'winner__username']
    readonly_fields = ['created_at', 'updated_at', 'total_players', 'total_derash']
    date_hierarchy = 'created_at'


@admin.register(GameCard)
class GameCardAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'user', 'card_number', 'is_winner', 'purchased_at']
    list_filter = ['is_winner', 'purchased_at', 'game']
    search_fields = ['user__username', 'card_number', 'game__id']
    readonly_fields = ['purchased_at']


@admin.register(CalledNumber)
class CalledNumberAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'letter', 'number', 'called_at']
    list_filter = ['game', 'letter', 'called_at']
    search_fields = ['game__id', 'number']
    readonly_fields = ['called_at']


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'amount', 'status', 'created_at', 'matched_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'bank_text']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['approve_deposits', 'reject_deposits']

    def approve_deposits(self, request, queryset):
        for deposit in queryset.filter(status='pending'):
            if deposit.match_texts():
                deposit.status = 'approved'
                deposit.matched_at = timezone.now()
                deposit.save()
                # Credit user balance
                from decimal import Decimal
                deposit.user.balance = Decimal(str(deposit.user.balance)) + Decimal(str(deposit.amount))
                deposit.user.save()
                # Create transaction
                Transaction.objects.create(
                    user=deposit.user,
                    transaction_type='deposit',
                    amount=deposit.amount,
                    deposit=deposit,
                    description=f'Deposit approved - Match ID: {deposit.id}'
                )
        self.message_user(request, f"{queryset.count()} deposits processed.")
    approve_deposits.short_description = "Approve selected deposits (if texts match)"

    def reject_deposits(self, request, queryset):
        queryset.filter(status='pending').update(status='rejected')
        self.message_user(request, f"{queryset.count()} deposits rejected.")
    reject_deposits.short_description = "Reject selected deposits"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'transaction_type', 'amount', 'game', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__username', 'description']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(GameSettings)
class GameSettingsAdmin(admin.ModelAdmin):
    """Singleton admin for game settings"""
    def has_add_permission(self, request):
        # Only allow one instance
        return not GameSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    fieldsets = (
        ('Game Timing', {
            'fields': ('time_between_calls', 'card_selection_timer')
        }),
        ('Financial Settings', {
            'fields': ('bid_amount', 'percentage_cut', 'min_withdraw')
        }),
        ('Card Settings', {
            'fields': ('total_cards',)
        }),
        ('Deposit Accounts', {
            'fields': ('deposit_accounts',),
            'description': 'Enter account holder name and account number for each platform'
        }),
        ('Support Settings', {
            'fields': ('support_phone',),
            'description': 'Support phone number for customer support'
        }),
    )


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'amount', 'platform', 'status', 'created_at']
    list_filter = ['status', 'platform', 'created_at']
    search_fields = ['user__username', 'user__phone_number', 'deposit_text']
    readonly_fields = ['created_at', 'updated_at', 'processed_at', 'processed_by']
    actions = ['approve_requests', 'reject_requests']
    
    def approve_requests(self, request, queryset):
        count = 0
        for deposit_request in queryset.filter(status='pending'):
            deposit_request.status = 'approved'
            deposit_request.processed_at = timezone.now()
            deposit_request.processed_by = request.user
            deposit_request.save()
            
            # Credit user balance
            deposit_request.user.balance = Decimal(str(deposit_request.user.balance)) + Decimal(str(deposit_request.amount))
            deposit_request.user.save()
            
            # Create transaction
            Transaction.objects.create(
                user=deposit_request.user,
                transaction_type='deposit',
                amount=deposit_request.amount,
                description=f'Deposit approved - {deposit_request.platform} - Request ID: {deposit_request.id}'
            )
            
            # Send notification to user via Telegram bot
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(
                    deposit_request.user.telegram_id,
                    f"✅ ገንዘቡ ገቢ ሆኗል!\n\n"
                    f"💰 መጠን: {deposit_request.amount} ብር\n"
                    f"🏦 ወደ: {deposit_request.platform}\n\n"
                    f"በሂሳብዎ ላይ ያለውን ለመመልከት /balance ይጫኑ።"
                )
            except Exception as e:
                pass
            
            count += 1
        self.message_user(request, f"{count} deposit requests approved.")
    approve_requests.short_description = "Approve selected deposit requests"
    
    def reject_requests(self, request, queryset):
        count = queryset.filter(status='pending').update(status='rejected', processed_at=timezone.now(), processed_by=request.user)
        
        # Send rejection notifications
        for deposit_request in queryset.filter(status='rejected'):
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(
                    deposit_request.user.telegram_id,
                    f"❌ የገንዘብ ማስገቢያ ጥያቄዎ ተቀባይነት አላገኘም።\n\n"
                    f"እባክዎ እንደገና ይሞክሩ።"
                )
            except Exception as e:
                pass
        
        self.message_user(request, f"{count} deposit requests rejected.")
    reject_requests.short_description = "Reject selected deposit requests"


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'amount', 'platform', 'account_holder_name', 'account_number', 'status', 'created_at']
    list_filter = ['status', 'platform', 'created_at']
    search_fields = ['user__username', 'user__phone_number', 'account_holder_name', 'account_number']
    readonly_fields = ['created_at', 'updated_at', 'processed_at', 'processed_by']
    actions = ['approve_requests', 'reject_requests']
    
    def approve_requests(self, request, queryset):
        count = 0
        for withdraw_request in queryset.filter(status='pending'):
            # Check if user has sufficient balance
            if withdraw_request.user.balance < withdraw_request.amount:
                continue
            
            withdraw_request.status = 'approved'
            withdraw_request.processed_at = timezone.now()
            withdraw_request.processed_by = request.user
            withdraw_request.save()
            
            # Deduct from user balance
            withdraw_request.user.balance = Decimal(str(withdraw_request.user.balance)) - Decimal(str(withdraw_request.amount))
            withdraw_request.user.save()
            
            # Create transaction
            Transaction.objects.create(
                user=withdraw_request.user,
                transaction_type='withdraw',
                amount=withdraw_request.amount,
                description=f'Withdrawal approved - {withdraw_request.platform} - Request ID: {withdraw_request.id}'
            )
            
            # Send notification to user via Telegram bot
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(
                    withdraw_request.user.telegram_id,
                    f"✅ ገንዘብ ተልኳል!\n\n"
                    f"💰 መጠን: {withdraw_request.amount} ብር\n"
                    f"🏦 ወደ: {withdraw_request.platform} ሂሳብ\n"
                    f"👤 የሂሳብ ባለቤት: {withdraw_request.account_holder_name}\n"
                    f"🔢 የሂሳብ ቁጥር: {withdraw_request.account_number}\n\n"
                    f"በሂሳብዎ ላይ ያለውን ለመመልከት /balance ይጫኑ።"
                )
            except Exception as e:
                pass
            
            count += 1
        self.message_user(request, f"{count} withdraw requests approved.")
    approve_requests.short_description = "Approve selected withdraw requests"
    
    def reject_requests(self, request, queryset):
        count = queryset.filter(status='pending').update(status='rejected', processed_at=timezone.now(), processed_by=request.user)
        
        # Send rejection notifications
        for withdraw_request in queryset.filter(status='rejected'):
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(
                    withdraw_request.user.telegram_id,
                    f"❌ የገንዘብ ማውጣት ጥያቄዎ ተቀባይነት አላገኘም።\n\n"
                    f"እባክዎ እንደገና ይሞክሩ።"
                )
            except Exception as e:
                pass
        
        self.message_user(request, f"{count} withdraw requests rejected.")
    reject_requests.short_description = "Reject selected withdraw requests"
