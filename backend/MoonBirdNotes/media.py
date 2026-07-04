import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView


class ProtectedMediaView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, path):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        requested_path = (media_root / path).resolve()

        try:
            requested_path.relative_to(media_root)
        except ValueError:
            raise Http404

        if not requested_path.is_file():
            raise Http404

        content_type, _ = mimetypes.guess_type(str(requested_path))
        return FileResponse(
            requested_path.open('rb'),
            content_type=content_type or 'application/octet-stream',
        )
