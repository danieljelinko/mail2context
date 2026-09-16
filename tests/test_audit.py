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


def _alternative_message(plain: str, html: str) -> EmailMessage:
    "A multipart/alternative message — the shape almost all Gmail mail arrives in."
    m = EmailMessage()
    m['Subject'] = 'S'
    m.set_content(plain)
    m.add_alternative(html, subtype='html')
    return m


def test_audit_messages_reports_no_loss_when_a_plain_part_omits_what_the_html_part_styles():
    # Given a multipart/alternative message whose HTML rendition carries a tracking URL and an
    # image alt that its plain rendition legitimately never had
    m = _alternative_message(
        plain='Newsletter for Palaiseau',
        html='<p>Newsletter for Palaiseau <a href="https://track.example.com/abcd1234">click</a>'
             '<img alt="AI4HU banner artwork" src="cid:x"></p>')

    # When we audit it
    rep = audit_messages([m])

    # Then the two renditions are not diffed against each other
    assert rep['messages_losing_text'] == 0
    assert rep['urls_dropped'] == 0
    assert rep['alts_dropped'] == 0


def test_audit_messages_audits_the_html_part_against_its_own_conversion():
    # Given an alternative message whose HTML rendition carries a long run its plain one omits
    m = _alternative_message(plain='Summary only.',
                             html='<p>Summary only. Reference ZZZ98765432 applies.</p>')

    # When we audit it
    rep = audit_messages([m])

    # Then the run is checked against the HTML conversion, which keeps it — not against the plain part
    assert rep['text_chunks_lost'] == 0


def test_audit_messages_does_not_count_an_anchor_the_renderer_is_right_to_drop():
    # Given HTML whose only http anchor sits in <head>, which the renderer decomposes by design
    m = EmailMessage()
    m['Subject'] = 'S'
    m.set_content('<html><head><a href="https://stats.example/beacon">b</a></head>'
                  '<body><p>Real content here</p></body></html>', subtype='html')

    # When we audit it
    rep = audit_messages([m])

    # Then a deliberate drop is not reported as loss
    assert rep['urls_dropped'] == 0


def test_audit_messages_does_not_count_a_url_whose_href_only_differs_by_surrounding_space():
    # Given an href carrying a trailing non-breaking space, which the renderer strips before
    # emitting — so comparing the raw attribute finds a mismatch that is not a loss
    m = EmailMessage()
    m['Subject'] = 'S'
    m.set_content('<p><a href="https://bit.ly/4qD0P2M\xa0">link</a></p>', subtype='html')

    # When we audit it
    rep = audit_messages([m])

    # Then the whitespace difference is not reported as a dropped URL
    assert rep['urls_dropped'] == 0
