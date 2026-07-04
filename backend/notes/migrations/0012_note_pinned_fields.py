from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0011_noteimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='note',
            name='pinned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='note',
            options={'ordering': ['-is_pinned', '-pinned_at', '-created_at']},
        ),
    ]
