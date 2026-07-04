from django.conf import settings
from django.middleware.csrf import get_token


def _cookie_kwargs(max_age):
    return {
        'max_age': max_age,
        'httponly': True,
        'secure': settings.JWT_COOKIE_SECURE,
        'samesite': settings.JWT_COOKIE_SAMESITE,
        'path': settings.JWT_COOKIE_PATH,
    }


def set_auth_cookies(response, access_token=None, refresh_token=None):
    if access_token is not None:
        response.set_cookie(
            settings.JWT_ACCESS_COOKIE_NAME,
            str(access_token),
            **_cookie_kwargs(int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())),
        )

    if refresh_token is not None:
        response.set_cookie(
            settings.JWT_REFRESH_COOKIE_NAME,
            str(refresh_token),
            **_cookie_kwargs(int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())),
        )


def clear_auth_cookies(response):
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        path=settings.JWT_COOKIE_PATH,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_COOKIE_PATH,
        samesite=settings.JWT_COOKIE_SAMESITE,
    )


def refresh_csrf_cookie(request):
    get_token(request)
