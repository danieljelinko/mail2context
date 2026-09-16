"Markdown → email-safe HTML. Deterministic, so drafts never need an LLM to produce their markup."
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

__all__ = ['render_markdown']

# Mail clients strip <style> blocks and class attributes, so every rule has to be inlined on the
# element itself. Keep this conservative: what renders in Proton, Gmail, Outlook and Thunderbird.
_BASE = 'font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.5; color: #222;'
_STYLES = {
    'p':          'margin: 0 0 1em 0;',
    'h1':         'font-size: 20px; font-weight: bold; margin: 0 0 0.6em 0;',
    'h2':         'font-size: 17px; font-weight: bold; margin: 1.2em 0 0.5em 0;',
    'h3':         'font-size: 15px; font-weight: bold; margin: 1.2em 0 0.4em 0;',
    'ul':         'margin: 0 0 1em 0; padding-left: 1.4em;',
    'ol':         'margin: 0 0 1em 0; padding-left: 1.4em;',
    'li':         'margin: 0 0 0.3em 0;',
    'a':          'color: #0b64c0;',
    'blockquote': 'margin: 0 0 1em 0; padding: 0.2em 0 0.2em 1em; '
                  'border-left: 3px solid #d0d0d0; color: #555;',
    'code':       'font-family: Consolas, Monaco, monospace; font-size: 13px; '
                  'background: #f4f4f4; padding: 0.1em 0.3em;',
    'pre':        'font-family: Consolas, Monaco, monospace; font-size: 13px; '
                  'background: #f4f4f4; padding: 0.8em; overflow-x: auto;',
    'table':      'border-collapse: collapse; margin: 0 0 1em 0;',
    'th':         'border: 1px solid #ccc; padding: 0.4em 0.6em; text-align: left; '
                  'background: #f4f4f4;',
    'td':         'border: 1px solid #ccc; padding: 0.4em 0.6em;',
    'hr':         'border: none; border-top: 1px solid #ddd; margin: 1.5em 0;',
}


def render_markdown(md: str) -> str:
    "Render `md` as self-contained HTML with inline styles, safe to use as a mail body."
    # html=False escapes raw HTML rather than passing it through. breaks=True keeps single
    # newlines as <br>: in a mail body a line break is meant, unlike in a document.
    # The commonmark preset has no tables; enable the GFM rule so _STYLES['table'] is reachable.
    md_it = MarkdownIt('commonmark', {'html': False, 'linkify': True, 'breaks': True}).enable('table')
    html = md_it.render(md)
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(True):
        style = _STYLES.get(tag.name)
        if style: tag['style'] = f"{tag.get('style', '')} {style}".strip()
    return f'<div style="{_BASE}">\n{soup!s}</div>'
