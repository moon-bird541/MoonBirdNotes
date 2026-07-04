from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from MoonBirdNotes.settings import build_cache_config

from .signals import ensure_default_superuser
from .throttles import AdminLoginRateThrottle
from .views import AdminLoginView


@override_settings(ADMIN_LOGIN_THROTTLE_RATE='5/minute')
class AdminLoginThrottleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    def tearDown(self):
        cache.clear()

    def _request(self, ip_address='203.0.113.10'):
        request = self.factory.post('/api/login/', {
            'username': 'admin',
            'password': 'wrong-password',
        }, format='json')
        request.META['REMOTE_ADDR'] = ip_address
        return request

    def test_admin_login_view_uses_login_throttle(self):
        self.assertIn(AdminLoginRateThrottle, AdminLoginView.throttle_classes)

    def test_blocks_sixth_login_attempt_from_same_ip(self):
        view = AdminLoginView()

        attempts = [
            AdminLoginRateThrottle().allow_request(self._request(), view)
            for _ in range(6)
        ]

        self.assertEqual(attempts[:5], [True, True, True, True, True])
        self.assertFalse(attempts[5])

    def test_login_throttle_tracks_ips_separately(self):
        view = AdminLoginView()

        for _ in range(5):
            same_ip_request = self._request('203.0.113.10')
            self.assertTrue(AdminLoginRateThrottle().allow_request(same_ip_request, view))

        blocked_request = self._request('203.0.113.10')
        other_ip_request = self._request('203.0.113.20')

        self.assertFalse(AdminLoginRateThrottle().allow_request(blocked_request, view))
        self.assertTrue(AdminLoginRateThrottle().allow_request(other_ip_request, view))

    @override_settings(ADMIN_LOGIN_THROTTLE_RATE='2/minute')
    def test_login_endpoint_returns_429_when_throttled(self):
        client = APIClient()
        payload = {
            'username': '',
            'password': '',
        }

        for _ in range(2):
            response = client.post('/api/login/', payload, format='json', REMOTE_ADDR='198.51.100.10')
            self.assertEqual(response.status_code, 400)

        response = client.post('/api/login/', payload, format='json', REMOTE_ADDR='198.51.100.10')

        self.assertEqual(response.status_code, 429)


class CacheSettingsTests(SimpleTestCase):
    def test_debug_can_use_local_memory_cache(self):
        caches = build_cache_config(debug=True, cache_url='')

        self.assertEqual(caches['default']['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')
        self.assertEqual(caches['default']['LOCATION'], 'moonbirdnotes-dev-cache')

    def test_cache_url_uses_shared_redis_cache(self):
        caches = build_cache_config(debug=False, cache_url='redis://127.0.0.1:6379/1')

        self.assertEqual(caches['default']['BACKEND'], 'django.core.cache.backends.redis.RedisCache')
        self.assertEqual(caches['default']['LOCATION'], 'redis://127.0.0.1:6379/1')

    def test_production_requires_cache_url(self):
        with self.assertRaises(ImproperlyConfigured):
            build_cache_config(debug=False, cache_url='')


class AdminCookieAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.csrf_client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='strong-password',
        )
        self.credentials = {
            'username': 'admin',
            'password': 'strong-password',
        }

    def _login(self, client=None):
        active_client = client or self.client
        response = active_client.post('/api/login/', self.credentials, format='json')
        self.assertEqual(response.status_code, 200)
        return response

    def test_login_sets_http_only_auth_cookies_and_returns_user_only(self):
        response = self._login()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['user']['username'], self.user.username)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertIn(settings.JWT_ACCESS_COOKIE_NAME, response.cookies)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[settings.JWT_ACCESS_COOKIE_NAME]['httponly'])
        self.assertTrue(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]['httponly'])
        self.assertEqual(response.cookies[settings.JWT_ACCESS_COOKIE_NAME]['path'], settings.JWT_COOKIE_PATH)
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE_NAME]['path'], settings.JWT_COOKIE_PATH)

    def test_session_endpoint_returns_current_user_from_auth_cookies(self):
        self._login()

        response = self.client.get('/api/session/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['id'], self.user.id)
        self.assertEqual(response.data['user']['username'], self.user.username)

    def test_refresh_uses_cookie_and_rotates_refresh_token(self):
        self._login()
        old_refresh_token = self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        old_refresh = RefreshToken(old_refresh_token)

        response = self.client.post('/api/token/refresh/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['detail'], 'Session refreshed.')
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertIn(settings.JWT_ACCESS_COOKIE_NAME, response.cookies)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertNotEqual(
            old_refresh_token,
            response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value,
        )
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=old_refresh['jti']).exists()
        )

    def test_logout_blacklists_refresh_cookie_and_clears_auth_cookies(self):
        self._login()
        old_refresh_token = self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        old_refresh = RefreshToken(old_refresh_token)

        response = self.client.post('/api/logout/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=old_refresh['jti']).exists()
        )
        self.assertEqual(response.cookies[settings.JWT_ACCESS_COOKIE_NAME].value, '')
        self.assertEqual(response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value, '')

        session_response = self.client.get('/api/session/')
        self.assertEqual(session_response.status_code, 401)

    def test_cookie_authenticated_write_requires_csrf_token(self):
        self._login(self.csrf_client)
        payload = {
            'title': 'CSRF 测试笔记',
            'markdown_content': '测试正文',
            'tag_names': ['安全测试'],
        }

        denied_response = self.csrf_client.post('/api/notes/create/', payload, format='json')
        self.assertEqual(denied_response.status_code, 403)

        allowed_response = self.csrf_client.post(
            '/api/notes/create/',
            payload,
            format='json',
            HTTP_X_CSRFTOKEN=self.csrf_client.cookies[settings.CSRF_COOKIE_NAME].value,
        )

        self.assertEqual(allowed_response.status_code, 201)
        self.assertEqual(allowed_response.data['title'], payload['title'])

    def test_logout_rejects_invalid_refresh_token(self):
        response = self.client.post('/api/logout/', {'refresh': 'not-a-token'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('refresh', response.data)


class DefaultSuperuserSignalTests(SimpleTestCase):
    @override_settings(ADMIN_USERNAME='admin', ADMIN_PASSWORD='default-password')
    def test_existing_admin_password_is_not_reset(self):
        admin_user = Mock(
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        user_model = Mock()
        user_model.objects.get_or_create.return_value = (admin_user, False)

        with patch('accounts.signals.get_user_model', return_value=user_model):
            ensure_default_superuser(sender=None)

        admin_user.set_password.assert_not_called()
        admin_user.save.assert_not_called()

    @override_settings(ADMIN_USERNAME='admin', ADMIN_PASSWORD='default-password')
    def test_created_admin_gets_default_password(self):
        admin_user = Mock(
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        user_model = Mock()
        user_model.objects.get_or_create.return_value = (admin_user, True)

        with patch('accounts.signals.get_user_model', return_value=user_model):
            ensure_default_superuser(sender=None)

        admin_user.set_password.assert_called_once_with('default-password')
        admin_user.save.assert_called_once()

    @override_settings(ADMIN_USERNAME='admin', ADMIN_PASSWORD='default-password')
    def test_existing_admin_permissions_are_repaired_without_resetting_password(self):
        admin_user = Mock(
            is_staff=False,
            is_superuser=False,
            is_active=False,
        )
        user_model = Mock()
        user_model.objects.get_or_create.return_value = (admin_user, False)

        with patch('accounts.signals.get_user_model', return_value=user_model):
            ensure_default_superuser(sender=None)

        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_active)
        admin_user.set_password.assert_not_called()
        admin_user.save.assert_called_once()
