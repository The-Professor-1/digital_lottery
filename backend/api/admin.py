from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from .models import User, Game, GameCard, CalledNumber, Deposit, Transaction, GameSettings, DepositRequest, TelebirrReceipt, CbeReceipt, WithdrawRequest, FailedDepositRequest, TotalStats, DailyStats
from decimal import Decimal


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'telegram_id', 'phone_number', 'unwithdrawable_balance', 'withdrawable_balance', 'total_games_played', 'total_wins', 'total_deposits_amount', 'total_withdrawals_amount', 'is_superuser', 'is_staff', 'created_at']
    list_filter = ['created_at', 'is_active', 'is_superuser', 'is_staff']
    search_fields = ['username', 'telegram_id', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Telegram Info', {'fields': ('telegram_id', 'phone_number')}),
        ('Balance', {'fields': ('unwithdrawable_balance', 'withdrawable_balance')}),
        ('Cached totals (survive prune)', {'fields': ('total_games_played', 'total_wins', 'total_deposits_amount', 'total_withdrawals_amount')}),
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
                # Credit user: deposits go to withdrawable_balance
                from decimal import Decimal
                from django.db.models import F
                User.objects.filter(id=deposit.user.id).update(withdrawable_balance=F('withdrawable_balance') + Decimal(str(deposit.amount)))
                deposit.user.refresh_from_db()
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
        ('Telebirr Auto-Verify', {
            'fields': ('telebirr_verify_api_key',),
            'description': 'API key for verifyapi.leulzenebe.pro. When set, Telebirr deposits are verified automatically from receipt text.'
        }),
        ('CBE Auto-Verify (same API)', {
            'fields': ('cbe_use_fallback_proxy',),
            'description': 'If your server is outside Ethiopia (e.g. AWS): enable to ask the verify API to use fallback proxy for CBE (skipPrimaryVerification). Leave off if hosting in Ethiopia.'
        }),
        ('Support Settings', {
            'fields': ('support_phone', 'instruction_text'),
            'description': 'Support phone for /support; instruction text for /instruction (leave empty for bot default).'
        }),
        ('Bot registration limit', {
            'fields': ('daily_new_start_limit',),
            'description': 'Max new /start (new user) registrations per calendar day. Set to 0 for no limit. Set to 1 to test (only one new user per day).'
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
            
            # Credit user: deposits go to withdrawable_balance
            from django.db.models import F
            User.objects.filter(id=deposit_request.user.id).update(withdrawable_balance=F('withdrawable_balance') + Decimal(str(deposit_request.amount)))
            deposit_request.user.refresh_from_db()
            
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


@admin.register(TelebirrReceipt)
class TelebirrReceiptAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'amount', 'created_at']
    list_filter = ['created_at']
    search_fields = ['reference', 'user__username']
    readonly_fields = ['created_at']


@admin.register(CbeReceipt)
class CbeReceiptAdmin(admin.ModelAdmin):
    list_display = ['reference', 'account_suffix', 'user', 'amount', 'created_at']
    list_filter = ['created_at']
    search_fields = ['reference', 'account_suffix', 'user__username']
    readonly_fields = ['created_at']


@admin.register(FailedDepositRequest)
class FailedDepositRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'platform', 'amount', 'failure_reason', 'reference', 'account_suffix', 'created_at']
    list_filter = ['platform', 'failure_reason', 'created_at']
    search_fields = ['user__username', 'reference', 'account_suffix', 'deposit_text', 'failure_reason']
    readonly_fields = ['created_at']


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
            if withdraw_request.user.withdrawable_balance < withdraw_request.amount:
                continue
            withdraw_request.status = 'approved'
            withdraw_request.processed_at = timezone.now()
            withdraw_request.processed_by = request.user
            withdraw_request.save()
            from django.db.models import F
            User.objects.filter(id=withdraw_request.user.id).update(withdrawable_balance=F('withdrawable_balance') - Decimal(str(withdraw_request.amount)))
            withdraw_request.user.refresh_from_db()
            
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


@admin.register(TotalStats)
class TotalStatsAdmin(admin.ModelAdmin):
    list_display = ['id', 'total_games', 'total_revenue', 'total_deposits', 'total_withdrawals', 'total_balance', 'updated_at']
    readonly_fields = ['total_games', 'total_revenue', 'total_deposits', 'total_withdrawals', 'total_balance', 'updated_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ['date', 'games_count', 'revenue', 'deposits', 'withdrawals', 'updated_at']
    list_filter = ['date']
    readonly_fields = ['date', 'games_count', 'revenue', 'deposits', 'withdrawals', 'updated_at']
    date_hierarchy = 'date'
