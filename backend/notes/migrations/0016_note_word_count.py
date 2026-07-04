import re

from django.db import migrations, models


def count_markdown_words(markdown_content):
    text = markdown_content or ''
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_~>#-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return len(re.sub(r'\s+', '', text))


def backfill_word_count(apps, schema_editor):
    Note = apps.get_model('notes', 'Note')
    notes = []

    for note in Note.objects.only('id', 'markdown_content').iterator():
        note.word_count = count_markdown_words(note.markdown_content)
        notes.append(note)

        if len(notes) >= 500:
            Note.objects.bulk_update(notes, ['word_count'], batch_size=500)
            notes = []

    if notes:
        Note.objects.bulk_update(notes, ['word_count'], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ('notes', '0015_alter_noteimage_image_upload_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='word_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_word_count, migrations.RunPython.noop),
    ]
