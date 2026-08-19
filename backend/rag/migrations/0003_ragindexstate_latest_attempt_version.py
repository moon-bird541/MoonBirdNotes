from django.db import migrations, models
from django.db.models import F


def reserve_legacy_attempt_version(apps, schema_editor):
    RagIndexState = apps.get_model('rag', 'RagIndexState')
    # 旧 Worker 可能在 Qdrant 留下 active_version + 1 的孤立 Point；保守跳过该版本。
    RagIndexState.objects.update(latest_attempt_version=F('index_version') + 1)


class Migration(migrations.Migration):
    dependencies = [
        ('rag', '0002_ragindexjob_available_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='ragindexstate',
            name='latest_attempt_version',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(
            reserve_legacy_attempt_version,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
