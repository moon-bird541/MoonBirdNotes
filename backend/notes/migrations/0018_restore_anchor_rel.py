import bleach
import markdown
from bleach.html5lib_shim import Filter
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
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'code': ['class'],
    'pre': ['class'],
    'div': ['class'],
    'span': ['class'],
    'h1': ['id'],
    'h2': ['id'],
    'h3': ['id'],
    'h4': ['id'],
    'h5': ['id'],
    'h6': ['id'],
}
ALLOWED_MARKDOWN_PROTOCOLS = ['http', 'https', 'mailto']


class AnchorRelFilter(Filter):
    def __iter__(self):
        for token in Filter.__iter__(self):
            if token.get('type') == 'StartTag' and token.get('name') == 'a':
                attributes = token.get('data', {})
                target = attributes.get((None, 'target'), '')

                if isinstance(target, str) and target.strip().lower() == '_blank':
                    rel_values = str(attributes.get((None, 'rel'), '')).split()
                    for required_rel in ('noopener', 'noreferrer'):
                        if required_rel not in rel_values:
                            rel_values.append(required_rel)
                    attributes[(None, 'rel')] = ' '.join(rel_values)

            yield token


def render_safe_markdown(markdown_content):
    html = markdown.markdown(
        markdown_content or '',
        extensions=['extra', 'fenced_code', 'tables', 'toc'],
    )

    cleaner = bleach.Cleaner(
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_MARKDOWN_PROTOCOLS,
        strip=True,
        filters=[AnchorRelFilter],
    )
    return cleaner.clean(html)


def restore_anchor_rel(apps, schema_editor):
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
        ('notes', '0017_restore_heading_ids'),
    ]

    operations = [
        migrations.RunPython(restore_anchor_rel, migrations.RunPython.noop),
    ]
