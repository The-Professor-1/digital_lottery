"""URL configuration for the Digital Lottery app."""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.conf import settings
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

    # Lottery admin (root + /api/ mirrors for axios baseURL)
    path('admin-dashboard/lottery-settings/', lottery_views.lottery_settings_admin, name='lottery-settings-admin'),
    path('admin-dashboard/lottery-restart-round/', lottery_views.lottery_force_restart_round, name='lottery-restart-round'),
    path('admin-dashboard/lottery-start-draw/', lottery_views.lottery_start_draw, name='lottery-start-draw'),
    path('admin-dashboard/lottery-purchases/', lottery_views.lottery_purchases_admin, name='lottery-purchases-admin'),
    path('admin-dashboard/lottery-purchases/<int:purchase_id>/action/', lottery_views.lottery_purchase_action, name='lottery-purchase-action'),
    path('admin-dashboard/lottery-announce-winner/', lottery_views.lottery_announce_winner, name='lottery-announce-winner'),
    path('admin-dashboard/lottery-bootstrap/', lottery_views.lottery_admin_bootstrap, name='lottery-admin-bootstrap'),
    path('admin-dashboard/lottery-users/', lottery_views.lottery_users_admin, name='lottery-users-admin'),
    path('admin-dashboard/lottery-users/delete/', lottery_views.lottery_user_delete, name='lottery-users-delete'),
    path('admin-dashboard/lottery-deleted/', lottery_views.lottery_deleted_admin, name='lottery-deleted-admin'),
    path('admin-dashboard/lottery-send-message/', lottery_views.lottery_send_message, name='lottery-send-message'),
    path('admin-dashboard/lottery-failed-deposits/', lottery_views.lottery_failed_deposits_admin, name='lottery-failed-deposits'),
    path('admin-dashboard/lottery-failed-deposits/<int:failed_id>/action/', lottery_views.lottery_failed_deposit_action, name='lottery-failed-deposit-action'),
    path('admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials'),
    path('admin-dashboard/login/', admin_views.admin_dashboard_login, name='admin-dashboard-login'),

    path('secondadmin/login/', admin_views.second_admin_login, name='second-admin-login'),
    path('secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout'),
    path('admin-view/login/', admin_views.second_admin_login, name='admin-view-login'),
    path('admin-view/logout/', admin_views.second_admin_logout, name='admin-view-logout'),

    path('api/admin-dashboard/lottery-settings/', lottery_views.lottery_settings_admin, name='lottery-settings-admin-api'),
    path('api/admin-dashboard/lottery-restart-round/', lottery_views.lottery_force_restart_round, name='lottery-restart-round-api'),
    path('api/admin-dashboard/lottery-start-draw/', lottery_views.lottery_start_draw, name='lottery-start-draw-api'),
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
    path('api/secondadmin/login/', admin_views.second_admin_login, name='second-admin-login-api'),
    path('api/secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout-api'),
    path('api/admin-view/login/', admin_views.second_admin_login, name='admin-view-login-api'),
    path('api/admin-view/logout/', admin_views.second_admin_logout, name='admin-view-logout-api'),

    path('api/', include('api.urls')),

    re_path(r'^assets/(?P<path>.*)$', serve, {
        'document_root': _frontend_assets_root(),
        'show_indexes': False,
    }),
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
        'show_indexes': False,
    }),
    re_path(
        r'^(?!admin/|api/|static/|assets/|media/).*$',
        serve_spa_index,
        name='frontend',
    ),
]

handler404 = 'api.error_handlers.json_404'

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
