from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class AdminLoginSerializer(TokenObtainPairSerializer):
    username_field = 'username'

    def _raise_login_error(self, detail, error_code):
        # Keep a stable error code so the frontend can render clear login feedback.
        raise serializers.ValidationError({
            'detail': detail,
            'error_code': error_code,
        })

    def _raise_invalid_credentials(self):
        self._raise_login_error('用户名或密码错误。', 'INVALID_CREDENTIALS')

    def validate(self, attrs):
        username = attrs.get(self.username_field, '').strip()
        password = attrs.get('password')
        user_model = get_user_model()

        if not username:
            self._raise_login_error('请输入用户名。', 'USERNAME_REQUIRED')

        if not password:
            self._raise_login_error('请输入密码。', 'PASSWORD_REQUIRED')

        # Keep failed login responses generic to avoid leaking whether a username exists.
        user = user_model.objects.filter(username=username).first()

        if not user:
            self._raise_invalid_credentials()

        if not user.check_password(password):
            self._raise_invalid_credentials()

        if not user.is_superuser:
            self._raise_invalid_credentials()

        if not user.is_active:
            self._raise_invalid_credentials()

        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'username': user.username,
                'is_superuser': user.is_superuser,
            },
        }


class AdminTokenRefreshSerializer(TokenRefreshSerializer):
    refresh = serializers.CharField(required=False)

    def validate(self, attrs):
        refresh_token = attrs.get('refresh') or self.context['request'].COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)

        if not refresh_token:
            raise serializers.ValidationError({'refresh': ['This field is required.']})

        return super().validate({
            **attrs,
            'refresh': refresh_token,
        })
