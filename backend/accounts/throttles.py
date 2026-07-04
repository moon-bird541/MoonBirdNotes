from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class AdminLoginRateThrottle(SimpleRateThrottle):
    scope = 'admin_login'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }

    def get_rate(self):
        return getattr(settings, 'ADMIN_LOGIN_THROTTLE_RATE', '5/minute')
