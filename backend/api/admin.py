"""Django admin registrations for lottery ops (bingo game admins removed from UI clutter)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    User,
    GameSettings,
    LotterySettings,
    LotteryPurchase,
    LotteryFailedDeposit,
    TelebirrReceipt,
    CbeReceipt,
    SecondAdmin,
    BroadcastMessage,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'username', 'telegram_id', 'phone_number',
        'is_superuser', 'is_staff', 'created_at',
    ]
    list_filter = ['created_at', 'is_active', 'is_superuser', 'is_staff']
    search_fields = ['username', 'telegram_id', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Telegram Info', {'fields': ('telegram_id', 'phone_number')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(GameSettings)
class GameSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'updated_at']


@admin.register(LotterySettings)
class LotterySettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'brand_name', 'display_name', 'draw_mode', 'ticket_price', 'updated_at']


@admin.register(LotteryPurchase)
class LotteryPurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'phone', 'status', 'amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['full_name', 'phone']


@admin.register(LotteryFailedDeposit)
class LotteryFailedDepositAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'created_at']
    list_filter = ['status']


@admin.register(TelebirrReceipt)
class TelebirrReceiptAdmin(admin.ModelAdmin):
    list_display = ['id', 'reference', 'amount', 'created_at']
    search_fields = ['reference']


@admin.register(CbeReceipt)
class CbeReceiptAdmin(admin.ModelAdmin):
    list_display = ['id', 'reference', 'account_suffix', 'amount', 'created_at']
    search_fields = ['reference']


@admin.register(SecondAdmin)
class SecondAdminAdmin(admin.ModelAdmin):
    list_display = ['id', 'username']


@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at']
    search_fields = ['message_text']
