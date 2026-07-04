import bleach
import markdown
from django.db import migrations


ALLOWED_MARKDOWN_TAGS = [
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'p',
    'br',
    'hr',
    'strong',
    'em',
    'u',
    's',
    'del',
    'ins',
    'a',
    'img',
    'ul',
    'ol',
    'li',
    'blockquote',
    'pre',
    'code',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
    'div',
    'span',
]
ALLOWED_MARKDOWN_ATTRIBUTES = {
    'a': ['href', 'title', 'target'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'code': ['class'],
    'pre': ['class'],
    'div': ['class'],
    'span': ['class'],
}
ALLOWED_MARKDOWN_PROTOCOLS = ['http', 'https', 'mailto']


def render_safe_markdown(markdown_content):
    html = markdown.markdown(
        markdown_content or '',
        extensions=['extra', 'fenced_code', 'tables', 'toc'],
    )

    return bleach.clean(
        html,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_MARKDOWN_PROTOCOLS,
        strip=True,
    )


def resanitize_rendered_html(apps, schema_editor):
    note_model = apps.get_model('notes', 'Note')
    version_model = apps.get_model('notes', 'NoteVersion')

    for note in note_model.objects.all().iterator():
        note.rendered_html = render_safe_markdown(note.markdown_content)
        note.save(update_fields=['rendered_html'])

    for version in version_model.objects.all().iterator():
        version.rendered_html = render_safe_markdown(version.markdown_content)
        version.save(update_fields=['rendered_html'])


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0009_alter_note_markdown_content_alter_note_rendered_html'),
    ]

    operations = [
        migrations.RunPython(resanitize_rendered_html, migrations.RunPython.noop),
    ]
