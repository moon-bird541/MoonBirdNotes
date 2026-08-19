import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('rag', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ragindexjob',
            name='available_at',
            # 已有任务迁移后立即可被 Worker 领取。
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddIndex(
            model_name='ragindexjob',
            index=models.Index(
                fields=['status', 'available_at'],
                name='rag_job_status_avail_idx',
            ),
        ),
    ]
