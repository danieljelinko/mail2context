from email.message import EmailMessage

from mail2context.audit import audit_messages, find_lost_chunks


def test_find_lost_chunks_reports_nothing_when_every_run_survives():
    # Given HTML whose long text runs all appear in the rendered output
    html = '<p>Engagement confirmed for Palaiseau</p>'
    rendered = 'Engagement confirmed for Palaiseau'

    # When we audit the conversion
    lost = find_lost_chunks(html, rendered)

    # Then nothing is reported lost
    assert lost == []


def test_find_lost_chunks_flags_a_run_the_renderer_dropped():
    # Given HTML containing a long run the rendered text omits
    html = '<p>Reference number ABC12345678 applies</p>'
    rendered = 'Reference number applies'

    # When we audit the conversion
    lost = find_lost_chunks(html, rendered)

    # Then the dropped run is named
    assert 'ABC12345678' in lost


def test_find_lost_chunks_ignores_whitespace_introduced_by_inline_markup():
    # Given text split across inline spans, which naive comparison reads as two tokens
    html = '<p><span>Mana</span><span>gement</span> of the ai4hu programme</p>'
    rendered = 'Management of the ai4hu programme'

    # When we audit the conversion
    lost = find_lost_chunks(html, rendered)

    # Then the split is not mistaken for loss
    assert lost == []


def test_audit_messages_counts_a_message_whose_link_target_is_preserved():
    # Given a message carrying a hyperlink
    m = EmailMessage()
    m['Subject'] = 'S'
    m.set_content('<p>See <a href="https://ai4hu.org/x">here</a></p>', subtype='html')

    # When we audit it
    rep = audit_messages([m])

    # Then no URL is reported dropped
    assert rep['urls_dropped'] == 0
