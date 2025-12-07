from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'games', views.GameViewSet, basename='game')
router.register(r'cards', views.GameCardViewSet, basename='card')

urlpatterns = [
    path('', include(router.urls)),
    path('health/', views.health_check, name='health-check'),
    path('auth/telegram/', views.authenticate_telegram, name='authenticate-telegram'),
    path('auth/telegram-register/', views.telegram_register, name='telegram-register'),
    path('wallet/', views.wallet_info, name='wallet-info'),
    path('wallet/deposit/', views.deposit, name='deposit'),
    path('wallet/withdraw/', views.withdraw, name='withdraw'),
    path('wallet/transfer/', views.transfer, name='transfer'),
    path('users/deposit/', views.deposit, name='deposit-legacy'),  # Legacy endpoint
    path('users/withdraw/', views.withdraw, name='withdraw-legacy'),  # Legacy endpoint
    # Admin endpoints
    path('admin/deposits/pending/', views.pending_deposits, name='pending-deposits'),
    path('admin/deposits/<int:deposit_id>/verify/', views.verify_deposit, name='verify-deposit'),
    path('admin/notify/', views.admin_notify, name='admin-notify'),
    path('admin/games/create/', views.create_game, name='create-game'),
    path('admin/games/<int:game_id>/start/', views.start_game, name='start-game'),
    path('admin/games/<int:game_id>/call-number/', views.call_number_admin, name='call-number'),
    path('admin/games/<int:game_id>/end/', views.end_game, name='end-game'),
    path('admin/games/restart/', views.restart_game, name='restart-game'),
    path('admin/send-telegram-message/', views.send_telegram_message, name='send-telegram-message'),
    # User management endpoints
    path('users/phone/', views.update_user_phone, name='update-user-phone'),
    path('admin/users/', views.admin_users_list, name='admin-users-list'),
    path('admin/users/<int:user_id>/', views.admin_user_detail, name='admin-user-detail'),
    path('admin/users/<int:user_id>/edit/', views.admin_user_edit, name='admin-user-edit'),
    path('admin/users/delete/', views.admin_users_delete, name='admin-users-delete'),
]

