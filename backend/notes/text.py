import re


def markdown_to_plain_text(markdown_content):
    text = markdown_content or ''
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[*_~>#-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def count_markdown_words(markdown_content):
    plain_text = markdown_to_plain_text(markdown_content)
    return len(re.sub(r'\s+', '', plain_text))
