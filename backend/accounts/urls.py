from django.urls import path

from .views import AdminLoginView, AdminLogoutView, AdminSessionView, AdminTokenRefreshView

urlpatterns = [
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),
    path('session/', AdminSessionView.as_view(), name='admin-session'),
    path('token/refresh/', AdminTokenRefreshView.as_view(), name='admin-token-refresh'),
]
