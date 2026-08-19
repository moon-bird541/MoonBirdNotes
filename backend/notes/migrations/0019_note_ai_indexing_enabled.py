from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('notes', '0018_restore_anchor_rel'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='ai_indexing_enabled',
            # 旧笔记默认不参与云端索引，必须由用户逐篇明确开启。
            field=models.BooleanField(default=False),
        ),
    ]
