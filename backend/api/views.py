"""Public API views for the lottery mini-app (auth + health). Bingo game APIs removed."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import User
from .serializers import UserSerializer
from .auth_utils import get_user_from_token
from .phone_utils import normalize_phone_number


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint to wake machines and verify app is running."""
    return Response({'status': 'ok', 'message': 'Service is healthy'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def authenticate_telegram(request):
    """Authenticate user from Telegram Web App init data."""
    init_data = request.data.get('init_data', '')
    token = request.data.get('token', '')

    if init_data:
        from api.telegram_auth import verify_telegram_init_data, get_or_create_user_from_telegram

        verified_data = verify_telegram_init_data(init_data)
        if verified_data and verified_data.get('user'):
            user = get_or_create_user_from_telegram(verified_data['user'])
            if user:
                from api.auth_utils import generate_jwt_token
                jwt_token = generate_jwt_token(user)
                serializer = UserSerializer(user)
                return Response({
                    **serializer.data,
                    'token': jwt_token,
                })

    if token:
        user = get_user_from_token(token)
        if user:
            serializer = UserSerializer(user)
            return Response(serializer.data)

    return Response({'error': 'Invalid init_data or token'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_register(request):
    """Register/authenticate user from Telegram Web App initData (lottery mini-app)."""
    init_data = request.data.get('initData') or request.data.get('init_data', '')

    if not init_data:
        return Response({'error': 'initData required'}, status=status.HTTP_400_BAD_REQUEST)

    from api.telegram_auth import verify_telegram_init_data, get_or_create_user_from_telegram
    from api.auth_utils import generate_jwt_token

    verified_data = verify_telegram_init_data(init_data)
    if not verified_data or not verified_data.get('user'):
        return Response({'error': 'Invalid initData signature'}, status=status.HTTP_401_UNAUTHORIZED)

    user = get_or_create_user_from_telegram(verified_data['user'])
    if not user:
        return Response({'error': 'Failed to create user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    jwt_token = generate_jwt_token(user)
    serializer = UserSerializer(user)
    return Response({
        'status': 'ok',
        'user_id': user.id,
        'user': serializer.data,
        'token': jwt_token,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_phone(request):
    """Update user phone number."""
    phone_number = request.data.get('phone_number', '').strip()

    if not phone_number:
        return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_phone = normalize_phone_number(phone_number)
    user = request.user
    user.phone_number = normalized_phone
    user.save(update_fields=['phone_number'])

    serializer = UserSerializer(user)
    return Response({
        'status': 'ok',
        'user': serializer.data,
    })
