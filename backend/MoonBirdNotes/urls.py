from django.contrib import admin
from django.urls import include, path

from .media import ProtectedMediaView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/notes/', include('notes.urls')),
    path('api/agent/', include('agent.urls')),
    path('api/', include('accounts.urls')),
    path('media/<path:path>', ProtectedMediaView.as_view(), name='protected-media'),
]
