from datetime import timedelta

from django.utils import timezone

from ..models import Note


def delete_note_files(note):
    if note.markdown_file:
        note.markdown_file.delete(save=False)

    for image in note.images.all():
        if image.image:
            image.image.delete(save=False)


def purge_expired_trash_notes(retention_days=30):
    expired_before = timezone.now() - timedelta(days=retention_days)
    expired_notes = Note.objects.filter(
        is_deleted=True,
        deleted_at__isnull=False,
        deleted_at__lt=expired_before,
    ).prefetch_related('images')
    deleted_count = 0

    for note in expired_notes:
        delete_note_files(note)
        note.delete()
        deleted_count += 1

    return deleted_count
