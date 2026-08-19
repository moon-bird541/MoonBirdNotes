from django.db import migrations, models


def enable_ai_indexing_for_existing_notes(apps, schema_editor):
    """只更新授权状态，不触发 signals、后台任务或任何外部网络请求。"""

    Note = apps.get_model('notes', 'Note')
    Note.objects.using(schema_editor.connection.alias).all().update(
        ai_indexing_enabled=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ('notes', '0019_note_ai_indexing_enabled'),
    ]

    operations = [
        # 回滚默认值时不批量关闭，避免覆盖迁移后用户逐篇调整过的授权状态。
        migrations.RunPython(
            enable_ai_indexing_for_existing_notes,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='note',
            name='ai_indexing_enabled',
            field=models.BooleanField(default=True),
        ),
    ]
