"""
ASGI config for the Digital Lottery project (HTTP only — bingo websockets removed).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')

application = get_asgi_application()
