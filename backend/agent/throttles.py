"""Knowledge Agent API 的按管理员账号限流。"""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class KnowledgeChatRateThrottle(SimpleRateThrottle):
    scope = 'knowledge_chat'

    def get_cache_key(self, request, view):
        if not getattr(request.user, 'is_authenticated', False):
            # 匿名请求会先被权限类拒绝，不占用任何已登录用户的额度。
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': f'user:{request.user.pk}',
        }

    def get_rate(self):
        return getattr(settings, 'AGENT_KNOWLEDGE_CHAT_RATE', '10/minute')
