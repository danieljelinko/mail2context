from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from mail2context.thread import group_threads, sent_at


@pytest.fixture
def make_msg() -> Callable[..., EmailMessage]:
    "Factory: build an `EmailMessage` carrying the headers threading relies on."
    def _build(msgid: str,                       # Message-ID, angle-bracketed ex.: "<a@x>"
               in_reply_to: str | None = None,   # parent's Message-ID
               refs: tuple[str, ...] = (),       # References chain, oldest first
               subj: str = 'Subject',
               secs: int = 0) -> EmailMessage:   # send time as offset from a fixed epoch
        m = EmailMessage()
        m['Message-ID'], m['Subject'] = msgid, subj
        m['Date'] = formatdate(1_700_000_000 + secs)
        if in_reply_to: m['In-Reply-To'] = in_reply_to
        if refs:        m['References'] = ' '.join(refs)
        m.set_content('body')
        return m
    return _build


def test_group_threads_joins_reply_to_parent_when_in_reply_to_matches(make_msg):
    # Given a root message and a reply pointing at it via In-Reply-To
    root  = make_msg('<a@x>')
    reply = make_msg('<b@x>', in_reply_to='<a@x>', secs=60)

    # When we group them into threads
    threads = group_threads([reply, root])

    # Then both messages land in one thread
    assert len(threads) == 1
    assert {m['Message-ID'] for m in threads[0]} == {'<a@x>', '<b@x>'}


def test_group_threads_orders_thread_oldest_first_when_input_is_shuffled(make_msg):
    # Given three chained messages handed over out of order
    a = make_msg('<a@x>', secs=0)
    b = make_msg('<b@x>', in_reply_to='<a@x>', secs=60)
    c = make_msg('<c@x>', in_reply_to='<b@x>', secs=120)

    # When we group them
    threads = group_threads([c, a, b])

    # Then the thread reads oldest-first
    assert [m['Message-ID'] for m in threads[0]] == ['<a@x>', '<b@x>', '<c@x>']


def test_group_threads_keeps_unrelated_messages_apart_when_no_headers_link_them(make_msg):
    # Given two messages that reference nothing in common
    a = make_msg('<a@x>', subj='Invoice')
    z = make_msg('<z@x>', subj='Lunch')

    # When we group them
    threads = group_threads([a, z])

    # Then each stands alone
    assert sorted(len(t) for t in threads) == [1, 1]


def test_group_threads_links_via_references_when_direct_parent_is_absent(make_msg):
    # Given a root and a grandchild whose own parent was never fetched
    root  = make_msg('<a@x>', secs=0)
    grand = make_msg('<c@x>', in_reply_to='<b@x>', refs=('<a@x>', '<b@x>'), secs=120)

    # When we group them without the missing middle message
    threads = group_threads([root, grand])

    # Then the References chain still binds them into one thread
    assert len(threads) == 1
    assert [m['Message-ID'] for m in threads[0]] == ['<a@x>', '<c@x>']


def test_group_threads_returns_every_message_exactly_once(make_msg):
    # Given a mix of chained and unrelated messages
    msgs = [make_msg('<a@x>'), make_msg('<b@x>', in_reply_to='<a@x>'),
            make_msg('<c@x>'), make_msg('<d@x>', refs=('<c@x>',)), make_msg('<e@x>')]

    # When we group them
    threads = group_threads(msgs)

    # Then the partition accounts for every input message, none dropped or duplicated
    assert sorted(id(m) for t in threads for m in t) == sorted(id(m) for m in msgs)


def test_group_threads_partitions_identically_when_input_order_changes(make_msg):
    # Given the same messages presented in two different orders
    def build():
        return [make_msg('<a@x>'), make_msg('<b@x>', in_reply_to='<a@x>'),
                make_msg('<c@x>'), make_msg('<d@x>', refs=('<c@x>', '<z@x>'))]
    forward, backward = build(), list(reversed(build()))

    # When we group each
    def shape(ms): return {frozenset(m['Message-ID'] for m in t) for t in group_threads(ms)}

    # Then the resulting partition is the same
    assert shape(forward) == shape(backward)


def test_thread_key_is_stable_for_the_same_thread(make_msg):
    # Given one thread built twice in different orders
    a, b = make_msg('<a@x>'), make_msg('<b@x>', in_reply_to='<a@x>', secs=60)

    # When we key each ordering
    from mail2context.thread import thread_key

    # Then the identifier does not change
    assert thread_key([a, b]) == thread_key([b, a])


def test_sent_at_orders_dates_that_string_comparison_would_scramble(make_msg):
    # Given two messages whose RFC 2822 Date headers start with different weekday names
    older = make_msg('<a@x>', secs=0)          # a Tuesday
    newer = make_msg('<b@x>', secs=4 * 86400)  # the following Saturday

    # When we sort them by parsed timestamp
    ordered = sorted([newer, older], key=sent_at)

    # Then chronology wins over the alphabetical accident of the weekday prefix
    assert [m['Message-ID'] for m in ordered] == ['<a@x>', '<b@x>']
    assert older['Date'][:3] > newer['Date'][:3]   # string order really is the opposite
