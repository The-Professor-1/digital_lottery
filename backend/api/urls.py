from django.urls import path
from . import views
from . import lottery_views

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('lottery/settings/', lottery_views.lottery_settings_public, name='lottery-settings-public'),
    path('lottery/me/', lottery_views.lottery_me, name='lottery-me'),
    path('lottery/language/', lottery_views.lottery_set_language, name='lottery-set-language'),
    path('lottery/tickets/', lottery_views.lottery_tickets, name='lottery-tickets'),
    path('lottery/purchase/', lottery_views.lottery_submit_purchase, name='lottery-purchase'),
    path('lottery/draw/', lottery_views.lottery_run_draw, name='lottery-draw'),
    path('lottery/notify-winners/', lottery_views.lottery_notify_winners, name='lottery-notify-winners'),
    path('lottery/next-round/', lottery_views.lottery_start_next_round, name='lottery-next-round'),
    path('auth/telegram/', views.authenticate_telegram, name='authenticate-telegram'),
    path('auth/telegram-register/', views.telegram_register, name='telegram-register'),
    path('users/phone/', views.update_user_phone, name='update-user-phone'),
]
