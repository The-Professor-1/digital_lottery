"""Admin auth endpoints for the lottery Vue dashboard (bingo admin APIs removed)."""
import json

from django.contrib.auth.hashers import check_password, make_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import SecondAdmin, User


@csrf_exempt
@require_http_methods(['POST'])
def admin_dashboard_login(request):
    """Inline login for admin dashboard: Django staff/superuser only."""
    from django.contrib.auth import authenticate, login

    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    username = data.get('username') or request.POST.get('username', '').strip()
    password = data.get('password') or request.POST.get('password', '')
    if not username or not password:
        return JsonResponse({'error': 'Username and password required'}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        try:
            u = User.objects.get(username=username)
            if u.check_password(password) and (u.is_staff or u.is_superuser) and u.is_active:
                user = u
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            pass
    if user is not None and (user.is_staff or user.is_superuser):
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        request.session.pop('second_admin_authenticated', None)
        request.session.pop('second_admin_username', None)
        return JsonResponse({'success': True, 'message': 'Logged in'})
    return JsonResponse({'error': 'Invalid credentials or not a staff user'}, status=401)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def second_admin_credentials_api(request):
    """Get/set Admin View (/admin-view) credentials — main staff only."""
    if not getattr(request.user, 'is_staff', False) and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if request.method == 'GET':
        try:
            second_admin = SecondAdmin.objects.first()
            if second_admin:
                return JsonResponse({
                    'username': second_admin.username,
                    'password': getattr(second_admin, 'password_plain', '') or '',
                    'has_password': bool(second_admin.password),
                })
        except Exception:
            pass
        return JsonResponse({'username': '', 'password': '', 'has_password': False})

    try:
        data = json.loads(request.body) if request.body else {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()

        if not username:
            return JsonResponse({'error': 'Username is required'}, status=400)

        second_admin, _created = SecondAdmin.objects.get_or_create(pk=1)
        second_admin.username = username
        if password:
            second_admin.password = make_password(password)
            second_admin.password_plain = password
        elif not second_admin.password:
            return JsonResponse({'error': 'Password is required for a new account'}, status=400)
        second_admin.save()

        return JsonResponse({
            'success': True,
            'message': 'Admin View credentials updated successfully',
            'username': second_admin.username,
            'password': second_admin.password_plain or '',
            'has_password': bool(second_admin.password),
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def second_admin_login(request):
    """Login for Admin View — session flag second_admin_authenticated."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.body else {}
            username = (data.get('username') or '').strip()
            password = (data.get('password') or '').strip()

            if not username or not password:
                return JsonResponse({'error': 'Username and password are required'}, status=400)

            try:
                second_admin = SecondAdmin.objects.get(username=username)
                if check_password(password, second_admin.password):
                    from django.contrib.auth import logout
                    logout(request)
                    request.session['second_admin_authenticated'] = True
                    request.session['second_admin_username'] = username
                    request.session.set_expiry(86400)
                    request.session.save()
                    return JsonResponse({'success': True, 'redirect': '/admin-view'})
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
            except SecondAdmin.DoesNotExist:
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
            except Exception:
                return JsonResponse({
                    'error': 'Database table not ready. Please run migrations first.',
                }, status=500)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Use the Admin View login page'}, status=405)


@csrf_exempt
@require_http_methods(['POST', 'GET'])
def second_admin_logout(request):
    """Logout for Admin View."""
    request.session.pop('second_admin_authenticated', None)
    request.session.pop('second_admin_username', None)
    return JsonResponse({'success': True, 'redirect': '/admin-view/login'})
