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
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from api import admin_views
import os

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin-dashboard/', admin_views.admin_dashboard, name='admin-dashboard'),
    path('admin-dashboard/search-user/', admin_views.search_user, name='search-user'),
    path('admin-dashboard/deposits/<int:deposit_id>/approve/', admin_views.approve_deposit_request_api, name='approve-deposit'),
    path('admin-dashboard/deposits/<int:deposit_id>/reject/', admin_views.reject_deposit_request_api, name='reject-deposit'),
    path('admin-dashboard/deposits/<int:deposit_id>/photo/', admin_views.get_deposit_photo, name='get-deposit-photo'),
    path('admin-dashboard/withdraws/<int:withdraw_id>/approve/', admin_views.approve_withdraw_request_api, name='approve-withdraw'),
    path('admin-dashboard/withdraws/<int:withdraw_id>/reject/', admin_views.reject_withdraw_request_api, name='reject-withdraw'),
    path('admin-dashboard/settings/', admin_views.game_settings_api, name='game-settings'),
    path('admin-dashboard/second-admin-credentials/', admin_views.second_admin_credentials_api, name='second-admin-credentials'),
    path('admin-dashboard/api/', admin_views.admin_dashboard_api, name='admin-dashboard-api'),
    path('admin-dashboard/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api'),
    path('secondadmin/login/', admin_views.second_admin_login, name='second-admin-login'),
    path('secondadmin/logout/', admin_views.second_admin_logout, name='second-admin-logout'),
    path('secondadmin/api/', admin_views.second_admin_dashboard_api, name='second-admin-dashboard-api'),
    path('secondadmin/api/refresh-deposits-withdrawals/', admin_views.refresh_deposits_withdrawals_api, name='refresh-deposits-withdrawals-api-second'),
    path('secondadmin/', admin_views.second_admin_dashboard, name='second-admin-dashboard'),
    path('api/', include('api.urls')),
    # Serve frontend assets (JS, CSS, etc.) as static files
    re_path(r'^assets/.*$', serve, {
        'document_root': os.path.join(settings.BASE_DIR, 'frontend_dist', 'assets'),
        'show_indexes': False
    }),
    # Serve frontend for all non-API routes (SPA routing)
    # Exclude: admin/, admin-dashboard/, api/, static/, assets/, secondadmin/
    re_path(r'^(?!admin/|admin-dashboard/|api/|static/|assets/|secondadmin/).*$', TemplateView.as_view(template_name='index.html'), name='frontend'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
