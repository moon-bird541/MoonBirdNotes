from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class AdminLoginSerializer(TokenObtainPairSerializer):
    username_field = 'username'

    def _raise_login_error(self, detail, error_code):
        # Keep a stable error code so the frontend can render clear login feedback.
        raise serializers.ValidationError({
            'detail': detail,
            'error_code': error_code,
        })

    def validate(self, attrs):
        username = attrs.get(self.username_field, '').strip()
        password = attrs.get('password')
        user_model = get_user_model()

        if not username:
            self._raise_login_error('请输入用户名。', 'USERNAME_REQUIRED')

        if not password:
            self._raise_login_error('请输入密码。', 'PASSWORD_REQUIRED')

        # Check the user first so we can distinguish "not registered" from "wrong password".
        user = user_model.objects.filter(username=username).first()

        if not user:
            self._raise_login_error('该用户未注册。', 'USER_NOT_FOUND')

        if not user.check_password(password):
            self._raise_login_error('密码错误。', 'PASSWORD_INCORRECT')

        if not user.is_superuser:
            self._raise_login_error('当前账号没有管理员登录权限。', 'NOT_SUPERUSER')

        if not user.is_active:
            self._raise_login_error('当前账号已被禁用。', 'ACCOUNT_DISABLED')

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
