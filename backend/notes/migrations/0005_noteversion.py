from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0004_tag_note_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='NoteVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('markdown_content', models.TextField()),
                ('rendered_html', models.TextField()),
                ('tag_names', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='notes.note')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
