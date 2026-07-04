from django.db import migrations, models

import notes.models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0014_diaryentry'),
    ]

    operations = [
        migrations.AlterField(
            model_name='noteimage',
            name='image',
            field=models.FileField(upload_to=notes.models.note_image_upload_to),
        ),
    ]
