from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .cookies import clear_auth_cookies, refresh_csrf_cookie, set_auth_cookies
from .serializers import AdminLoginSerializer, AdminTokenRefreshSerializer
from .throttles import AdminLoginRateThrottle


def build_user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'is_superuser': user.is_superuser,
    }


class AdminLoginView(TokenObtainPairView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = AdminLoginSerializer
    throttle_classes = [AdminLoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code != status.HTTP_200_OK:
            return response

        access_token = response.data.pop('access', None)
        refresh_token = response.data.pop('refresh', None)
        user_payload = response.data.get('user')

        if not access_token or not refresh_token or not user_payload:
            return Response({'detail': '登录响应缺少必要字段。'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
        refresh_csrf_cookie(request)
        response.data = {
            'user': user_payload,
        }
        return response


class AdminTokenRefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = AdminTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code != status.HTTP_200_OK:
            return response

        access_token = response.data.pop('access', None)
        refresh_token = response.data.pop('refresh', None)

        if access_token:
            set_auth_cookies(response, access_token=access_token)

        if refresh_token:
            set_auth_cookies(response, refresh_token=refresh_token)

        refresh_csrf_cookie(request)
        response.data = {'detail': 'Session refreshed.'}
        return response


class AdminLogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh') or request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        response = Response({'detail': 'Logged out.'}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)

        if not refresh_token:
            return response

        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            response.data = {'refresh': ['Refresh token is invalid or expired.']}
            response.status_code = status.HTTP_400_BAD_REQUEST

        return response


class AdminSessionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            response = Response({'detail': 'Not authenticated.'}, status=status.HTTP_401_UNAUTHORIZED)
            refresh_csrf_cookie(request)
            return response

        response = Response({
            'user': build_user_payload(request.user),
        }, status=status.HTTP_200_OK)
        refresh_csrf_cookie(request)
        return response
