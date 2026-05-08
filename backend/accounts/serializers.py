from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class AdminLoginSerializer(TokenObtainPairSerializer):
    username_field = 'username'

    def validate(self, attrs):
        # 先按用户名查找账号，便于返回更明确的登录失败提示。
        username = attrs.get(self.username_field, '').strip()
        password = attrs.get('password')
        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()

        if not user:
            raise serializers.ValidationError({'detail': '该用户未注册。'})

        if not user.check_password(password):
            raise serializers.ValidationError({'detail': '密码错误。'})

        # 当前系统仅允许固定的超级管理员账号登录。
        if username != settings.ADMIN_USERNAME:
            raise serializers.ValidationError({'detail': '当前账号未开放登录权限。'})

        if not user.is_superuser:
            raise serializers.ValidationError({'detail': '当前账号不是超级管理员。'})

        if not user.is_active:
            raise serializers.ValidationError({'detail': '当前账号已被禁用。'})

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
