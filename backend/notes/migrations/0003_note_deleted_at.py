from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0002_note_is_deleted'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
