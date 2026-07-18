"""bingo URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import HttpResponse, Http404
from api import admin_views
from api import lottery_views
import os


def serve_spa_index(request):
    """Serve the SPA index.html from the resolved FRONTEND_DIST (newest build)."""
    dist = getattr(settings, 'FRONTEND_DIST', None)
    if not dist:
        raise Http404('Frontend not configured')
    abs_path = os.path.join(str(dist), 'index.html')
    if not os.path.isfile(abs_path):
        # Fallback search
        base = str(getattr(settings, 'BASE_DIR', ''))
        for path in (
            os.path.join(base, 'frontend_dist', 'index.html'),
            os.path.join(base, '..', 'frontend_dist', 'index.html'),
        ):
            if os.path.isfile(os.path.abspath(path)):
                abs_path = os.path.abspath(path)
                break
        else:
            raise Http404('index.html not found')
    with open(abs_path, 'r', encoding='utf-8') as f:
        response = HttpResponse(f.read(), content_type='text/html')
    # Always revalidate HTML so Telegram WebView picks up new hashed JS after rebuild
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    return response


def _frontend_assets_root():
    dist = getattr(settings, 'FRONTEND_DIST', None)
    if dist:
        assets = os.path.join(str(dist), 'assets')
        if os.path.isdir(assets):
            return assets
    base = str(getattr(settings, 'BASE_DIR', ''))
    for candidate in (
        os.path.join(base, 'frontend_dist', 'assets'),
        os.path.join(base, '..', 'frontend_dist', 'assets'),
    ):
        abs_c = os.path.abspath(candidate)
        if os.path.isdir(abs_c):
            return abs_c
    return os.path.join(base, 'frontend_dist', 'assets')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin', RedirectView.as_view(url='/admin/', permanent=True)),
    # Admin dashboard and secondadmin PAGE routes removed so SPA (index.html) is served for /admin-dashboard and /secondadmin
    path('admin-dashboard/search-user/', admin_views.search_user, name='search-user'),
    path('admin-dashboard/users/<int:user_id>/balance/', admin_views.update_user_balance, name='update-user-balance'),
    path('admin-dashboard/search-transaction/', admin_views.search_transaction, name='search-transaction'),
    path('admin-dashboard/cbe-receipt-ref/add/', admin_views.add_cbe_receipt_ref_api, name='add-cbe-receipt-ref'),
    path('admin-dashboard/cbe-receipt-ref/delete/', admin_views.delete_cbe_receipt_ref_api, name='delete-cbe-receipt-ref'),
    path('admin-dashboard/telebirr-receipt-ref/add/', admin_views.add_telebirr_receipt_ref_api, name='add-telebirr-receipt-ref'),
    path('admin-dashboard/telebirr-receipt-ref/delete/', admin_views.delete_telebirr_receipt_ref_api, name='delete-telebirr-receipt-ref'),
    path('admin-dashboard/deposits/pending/bulk-delete/', admin_views.bulk_delete_pending_deposits_api, name='bulk-delete-pending-deposits'),
    path('admin-dashboard/deposits/<int:deposit_id>/approve/', admin_views.approve_deposit_request_api, name='approve-deposit'),
    path('admin-dashboard/deposits/<int:deposit_id>/reject/', admin_views.reject_deposit_request_api, name='reject-deposit'),
    path('admin-dashboard/deposits/<int:deposit_id>/photo/', admin_views.get_deposit_photo, name='get-deposit-photo'),
    path('admin-dashboard/failed-deposits/bulk-delete/', admin_views.bulk_delete_failed_deposits_api, name='bulk-delete-failed-deposits'),
    path('admin-dashboard/failed-deposits/<int:failed_id>/delete/', admin_views.delete_failed_deposit_api, name='delete-failed-deposit'),
    path('admin-dashboard/failed-deposits/<int:failed_id>/approve/', admin_views.approve_failed_deposit_api, name='approve-failed-deposit'),
    path('admin-dashboard/withdraws/<int:withdraw_id>/approve/', admin_views.approve_withdraw_request_api, name='approve-withdraw'),
    path('admin-dashboard/withdraws/<int:withdraw_id>/reject/', admin_views.reject_withdraw_request_api, name='reject-withdraw'),
    path('admin-dashboard/withdraws/<int:withdraw_id>/delete/', admin_views.delete_withdraw_request_api, name='delete-withdraw'),
    path('admin-dashboard/settings/', admin_views.game_settings_api, name='game-settings'),
    path('admin-dashboard/lottery-settings/', lottery_views.lottery_settings_admin, name='lottery-settings-admin'),
    path('admin-dashboard/lottery-purchases/', lottery_views.lottery_purchases_admin, name='lottery-purchases-admin'),
    path('admin-dashboard/lottery-purchases/<int:purchase_id>/action/', lottery_views.lottery_purchase_action, name='lottery-purchase-action'),
    path('admin-dashboard/lottery-announce-winner/', lottery_views.lottery_announce_winner, name='lottery-announce-winner'),
    path('admin-dashboard/lottery-bootstrap/', lottery_views.lottery_admin_bootstrap, name='lottery-admin-bootstrap'),
    path('admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials'),
    path('admin-dashboard/login/', admin_views.admin_dashboard_login, name='admin-dashboard-login'),
    path('admin-dashboard/api/', admin_views.admin_dashboard_api, name='admin-dashboard-api'),
    path('admin-dashboard/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api'),
    path('secondadmin/login/', admin_views.second_admin_login, name='second-admin-login'),
    path('secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout'),
    path('secondadmin/api/', admin_views.second_admin_dashboard_api, name='second-admin-dashboard-api'),
    path('secondadmin/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-second'),
    # Prefer Admin View path names (same handlers)
    path('admin-view/login/', admin_views.second_admin_login, name='admin-view-login'),
    path('admin-view/logout/', admin_views.second_admin_logout, name='admin-view-logout'),
    path('admin-view/api/', admin_views.second_admin_dashboard_api, name='admin-view-dashboard-api'),
    path('admin-dashboard/lottery-users/', lottery_views.lottery_users_admin, name='lottery-users-admin'),
    path('admin-dashboard/lottery-users/delete/', lottery_views.lottery_user_delete, name='lottery-users-delete'),
    path('admin-dashboard/lottery-deleted/', lottery_views.lottery_deleted_admin, name='lottery-deleted-admin'),
    path('admin-dashboard/lottery-send-message/', lottery_views.lottery_send_message, name='lottery-send-message'),
    path('admin-dashboard/lottery-failed-deposits/', lottery_views.lottery_failed_deposits_admin, name='lottery-failed-deposits'),
    path('admin-dashboard/lottery-failed-deposits/<int:failed_id>/action/', lottery_views.lottery_failed_deposit_action, name='lottery-failed-deposit-action'),
    # secondadmin/ page route removed so SPA serves /secondadmin
    # Duplicate admin/secondadmin API routes under /api/ so requests to /api/admin-dashboard/api/ etc. work (e.g. if frontend uses api baseURL)
    path('api/admin-dashboard/search-user/', admin_views.search_user, name='search-user-api'),
    path('api/admin-dashboard/users/<int:user_id>/balance/', admin_views.update_user_balance, name='update-user-balance-api'),
    path('api/admin-dashboard/search-transaction/', admin_views.search_transaction, name='search-transaction-api'),
    path('api/admin-dashboard/cbe-receipt-ref/add/', admin_views.add_cbe_receipt_ref_api, name='add-cbe-receipt-ref-api'),
    path('api/admin-dashboard/cbe-receipt-ref/delete/', admin_views.delete_cbe_receipt_ref_api, name='delete-cbe-receipt-ref-api'),
    path('api/admin-dashboard/telebirr-receipt-ref/add/', admin_views.add_telebirr_receipt_ref_api, name='add-telebirr-receipt-ref-api'),
    path('api/admin-dashboard/telebirr-receipt-ref/delete/', admin_views.delete_telebirr_receipt_ref_api, name='delete-telebirr-receipt-ref-api'),
    path('api/admin-dashboard/deposits/pending/bulk-delete/', admin_views.bulk_delete_pending_deposits_api, name='bulk-delete-pending-deposits-api'),
    path('api/admin-dashboard/deposits/<int:deposit_id>/approve/', admin_views.approve_deposit_request_api, name='approve-deposit-api'),
    path('api/admin-dashboard/deposits/<int:deposit_id>/reject/', admin_views.reject_deposit_request_api, name='reject-deposit-api'),
    path('api/admin-dashboard/deposits/<int:deposit_id>/photo/', admin_views.get_deposit_photo, name='get-deposit-photo-api'),
    path('api/admin-dashboard/failed-deposits/bulk-delete/', admin_views.bulk_delete_failed_deposits_api, name='bulk-delete-failed-deposits-api'),
    path('api/admin-dashboard/failed-deposits/<int:failed_id>/delete/', admin_views.delete_failed_deposit_api, name='delete-failed-deposit-api'),
    path('api/admin-dashboard/failed-deposits/<int:failed_id>/approve/', admin_views.approve_failed_deposit_api, name='approve-failed-deposit-api'),
    path('api/admin-dashboard/withdraws/pending/bulk-delete/', admin_views.bulk_delete_pending_withdraws_api, name='bulk-delete-pending-withdraws-api'),
    path('api/admin-dashboard/withdraws/<int:withdraw_id>/approve/', admin_views.approve_withdraw_request_api, name='approve-withdraw-api'),
    path('api/admin-dashboard/withdraws/<int:withdraw_id>/reject/', admin_views.reject_withdraw_request_api, name='reject-withdraw-api'),
    path('api/admin-dashboard/withdraws/<int:withdraw_id>/delete/', admin_views.delete_withdraw_request_api, name='delete-withdraw-api'),
    path('api/admin-dashboard/settings/', admin_views.game_settings_api, name='game-settings-api'),
    path('api/admin-dashboard/lottery-settings/', lottery_views.lottery_settings_admin, name='lottery-settings-admin-api'),
    path('api/admin-dashboard/lottery-purchases/', lottery_views.lottery_purchases_admin, name='lottery-purchases-admin-api'),
    path('api/admin-dashboard/lottery-purchases/<int:purchase_id>/action/', lottery_views.lottery_purchase_action, name='lottery-purchase-action-api'),
    path('api/admin-dashboard/lottery-announce-winner/', lottery_views.lottery_announce_winner, name='lottery-announce-winner-api'),
    path('api/admin-dashboard/lottery-bootstrap/', lottery_views.lottery_admin_bootstrap, name='lottery-admin-bootstrap-api'),
    path('api/admin-dashboard/lottery-users/', lottery_views.lottery_users_admin, name='lottery-users-admin-api'),
    path('api/admin-dashboard/lottery-users/delete/', lottery_views.lottery_user_delete, name='lottery-users-delete-api'),
    path('api/admin-dashboard/lottery-deleted/', lottery_views.lottery_deleted_admin, name='lottery-deleted-admin-api'),
    path('api/admin-dashboard/lottery-send-message/', lottery_views.lottery_send_message, name='lottery-send-message-api'),
    path('api/admin-dashboard/lottery-failed-deposits/', lottery_views.lottery_failed_deposits_admin, name='lottery-failed-deposits-api'),
    path('api/admin-dashboard/lottery-failed-deposits/<int:failed_id>/action/', lottery_views.lottery_failed_deposit_action, name='lottery-failed-deposit-action-api'),
    path('api/admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials-api'),
    path('api/admin-dashboard/login/', admin_views.admin_dashboard_login, name='admin-dashboard-login-api'),
    path('api/admin-dashboard/api/', admin_views.admin_dashboard_api, name='admin-dashboard-api-alt'),
    path('api/admin-dashboard/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-alt'),
    path('api/secondadmin/login/', admin_views.second_admin_login, name='second-admin-login-api'),
    path('api/secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout-api'),
    path('api/secondadmin/api/', admin_views.second_admin_dashboard_api, name='second-admin-dashboard-api-alt'),
    path('api/secondadmin/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-second-alt'),
    path('api/admin-view/login/', admin_views.second_admin_login, name='admin-view-login-api'),
    path('api/admin-view/logout/', admin_views.second_admin_logout, name='admin-view-logout-api'),
    path('api/admin-view/api/', admin_views.second_admin_dashboard_api, name='admin-view-dashboard-api-alt'),
    path('api/', include('api.urls')),
    # Serve frontend assets (JS, CSS, etc.) from the active Vite build
    re_path(r'^assets/(?P<path>.*)$', serve, {
        'document_root': _frontend_assets_root(),
        'show_indexes': False
    }),
    # Uploaded car photos / receipts (must work in production, not only DEBUG)
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
        'show_indexes': False
    }),
    # Serve frontend for all non-API routes (SPA routing)
    # Use serve_spa_index so index.html is loaded from filesystem (works when frontend_dist is beside backend on EC2)
    re_path(r'^(?!admin/|api/|static/|assets/|media/|admin-dashboard/(?:lottery-|login|api|search-user|users|deposits|failed-deposits|withdraws|settings|second-admin)).*$', serve_spa_index, name='frontend'),
]

handler404 = 'api.error_handlers.json_404'

# Serve static / media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
