from mail2context.markdown_mail import render_markdown


def test_render_markdown_sets_a_proportional_font_so_mail_is_not_monospace():
    # Given any body at all
    html = render_markdown('Bonjour')

    # When it is rendered
    # Then the wrapper carries an explicit sans-serif family, the whole point of the exercise
    assert 'font-family' in html
    assert 'monospace' not in html.split('<code')[0]


def test_render_markdown_turns_emphasis_into_tags():
    # Given markdown emphasis
    html = render_markdown('This is **bold** and *italic*.')

    # When rendered
    # Then it becomes real markup rather than literal asterisks
    assert '<strong>bold</strong>' in html
    assert '<em>italic</em>' in html
    assert '**' not in html


def test_render_markdown_renders_a_link_with_its_target():
    # Given a markdown link
    html = render_markdown('See [the lab](https://lab.ai4hu.org).')

    # When rendered
    # Then the anchor carries the href
    assert 'href="https://lab.ai4hu.org"' in html
    assert '>the lab</a>' in html


def test_render_markdown_renders_bullets_as_a_list():
    # Given a markdown bullet list
    html = render_markdown('Points:\n\n- first\n- second\n')

    # When rendered
    # Then it becomes a real list, not three loose lines
    assert '<ul' in html
    assert html.count('<li') == 2


def test_render_markdown_inlines_styles_because_clients_strip_style_blocks():
    # Given a heading and a paragraph
    html = render_markdown('# Title\n\nText.\n')

    # When rendered
    # Then styling is inline on the elements, with no <style> block to be stripped
    assert '<style' not in html
    assert 'style="' in html


def test_render_markdown_escapes_html_so_a_body_cannot_inject_markup():
    # Given a body containing raw HTML
    html = render_markdown('Coût < 100 & <script>alert(1)</script>')

    # When rendered
    # Then the script is not emitted as live markup
    assert '<script>' not in html
    assert '&lt;' in html


def test_render_markdown_keeps_a_hard_wrapped_paragraph_as_one_paragraph():
    # Given a paragraph the author happened to wrap across lines
    html = render_markdown('Je vous ai transmis le 31 août\nles justificatifs.')

    # When rendered
    # Then it is one paragraph, since markdown joins soft-wrapped lines
    assert html.count('<p') == 1
