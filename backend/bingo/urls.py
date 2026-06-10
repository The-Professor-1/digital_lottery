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
import os


def serve_spa_index(request):
    """Serve the SPA index.html from frontend_dist (tries backend/frontend_dist and repo root frontend_dist)."""
    base = getattr(settings, 'BASE_DIR', None)
    if base is None:
        raise Http404('Frontend not configured')
    # Path can be Path or str
    base = str(base)
    candidates = [
        os.path.join(base, 'frontend_dist', 'index.html'),
        os.path.join(base, '..', 'frontend_dist', 'index.html'),
    ]
    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                return HttpResponse(f.read(), content_type='text/html')
    raise Http404('index.html not found')

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
    path('admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials'),
    path('admin-dashboard/login/', admin_views.admin_dashboard_login, name='admin-dashboard-login'),
    path('admin-dashboard/api/', admin_views.admin_dashboard_api, name='admin-dashboard-api'),
    path('admin-dashboard/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api'),
    path('secondadmin/login/', admin_views.second_admin_login, name='second-admin-login'),
    path('secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout'),
    path('secondadmin/api/', admin_views.second_admin_dashboard_api, name='second-admin-dashboard-api'),
    path('secondadmin/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-second'),
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
    path('api/admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials-api'),
    path('api/admin-dashboard/login/', admin_views.admin_dashboard_login, name='admin-dashboard-login-api'),
    path('api/admin-dashboard/api/', admin_views.admin_dashboard_api, name='admin-dashboard-api-alt'),
    path('api/admin-dashboard/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-alt'),
    path('api/secondadmin/login/', admin_views.second_admin_login, name='second-admin-login-api'),
    path('api/secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout-api'),
    path('api/secondadmin/api/', admin_views.second_admin_dashboard_api, name='second-admin-dashboard-api-alt'),
    path('api/secondadmin/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-second-alt'),
    path('api/', include('api.urls')),
    # Serve frontend assets (JS, CSS, etc.) as static files
    re_path(r'^assets/.*$', serve, {
        'document_root': os.path.join(settings.BASE_DIR, 'frontend_dist', 'assets'),
        'show_indexes': False
    }),
    # Serve frontend for all non-API routes (SPA routing)
    # Use serve_spa_index so index.html is loaded from filesystem (works when frontend_dist is beside backend on EC2)
    re_path(r'^(?!admin/|api/|static/|assets/).*$', serve_spa_index, name='frontend'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
