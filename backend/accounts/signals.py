from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver


@receiver(post_migrate)
def ensure_default_superuser(sender, **kwargs):
    try:
        user_model = get_user_model()
        admin_user, created = user_model.objects.get_or_create(
            username=settings.ADMIN_USERNAME,
            defaults={
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            },
        )
    except (OperationalError, ProgrammingError):
        return

    updated = False

    if created or not admin_user.check_password(settings.ADMIN_PASSWORD):
        admin_user.set_password(settings.ADMIN_PASSWORD)
        updated = True

    if not admin_user.is_staff:
        admin_user.is_staff = True
        updated = True

    if not admin_user.is_superuser:
        admin_user.is_superuser = True
        updated = True

    if not admin_user.is_active:
        admin_user.is_active = True
        updated = True

    if updated:
        admin_user.save()
