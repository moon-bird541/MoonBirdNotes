from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0002_knowledgeconversation_memory_summary_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowledgeconversationturn',
            name='run_trace',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
