from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0012_note_pinned_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='importance',
            field=models.DecimalField(
                decimal_places=1,
                default=0,
                max_digits=2,
                validators=[MinValueValidator(0), MaxValueValidator(5)],
            ),
        ),
    ]
