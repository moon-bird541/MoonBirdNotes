from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import AdminLoginSerializer


class AdminLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = AdminLoginSerializer


class AdminTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
