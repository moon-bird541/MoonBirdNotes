from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('rag', '0003_ragindexstate_latest_attempt_version'),
    ]

    operations = [
        migrations.CreateModel(
            name='RagIndexDeletionJob',
            fields=[
                ('note_id', models.PositiveIntegerField(primary_key=True, serialize=False)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('indexing', 'Indexing'),
                            ('completed', 'Completed'),
                            ('failed', 'Failed'),
                        ],
                        default='pending',
                        max_length=16,
                    ),
                ),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('available_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [
                    models.Index(
                        fields=['status', 'available_at'],
                        name='rag_delete_status_avail_idx',
                    ),
                ],
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(
                            ('status__in', ['pending', 'indexing', 'completed', 'failed'])
                        ),
                        name='rag_delete_job_status_valid',
                    ),
                ],
            },
        ),
    ]
