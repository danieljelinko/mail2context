"""TEMPORARY round-trip assertions — D-011. Deleted with the send path at `01_plan.md` Phase 6.

Pure functions over already-fetched messages: no IMAP, no SMTP. They exist so the verdict of
`just verify-roundtrip` is itself testable — a checker that cannot fail proves nothing (see the
`bridge-status` row in `04_learnings.md`).
"""
import re
from email.message import EmailMessage

from .thread import group_threads, message_id, sent_at

__all__ = ['check_reply_chain', 'check_thread']

# thread.py keeps its own copy private; this module is deleted at Phase 6, so a local pattern is
# cheaper than widening that module's public surface for a temporary caller.
_IDS = re.compile(r'<[^<>]+>')


def check_thread(msgs: list[EmailMessage],
                 expected_ids: list[str],  # delivered Message-IDs, in the order they were sent
                 ) -> list[str]:
    "Problems rebuilding `msgs` into ONE thread holding `expected_ids` in order; empty means good."
    threads = group_threads(msgs)
    if len(threads) != 1:
        sizes = ', '.join(f'{len(t)} msg' for t in sorted(threads, key=len, reverse=True))
        return [f'rebuilt {len(threads)} threads ({sizes}), expected exactly 1']
    got = [message_id(m) for m in sorted(threads[0], key=sent_at)]
    if len(got) != len(expected_ids):
        return [f'thread holds {len(got)} messages, expected {len(expected_ids)}']
    if got != expected_ids:
        return [f'thread order differs from send order:\n  got  {got}\n  want {expected_ids}']
    return []


def check_reply_chain(msgs: list[EmailMessage],
                      expected_ids: list[str],  # delivered Message-IDs, in the order they were sent
                      ) -> list[str]:
    "Problems in the DELIVERED In-Reply-To/References of `expected_ids`; empty means they survived."
    by_id = {message_id(m): m for m in msgs}
    problems = []
    for i, mid in enumerate(expected_ids[1:], start=1):
        m = by_id.get(mid)
        if m is None: problems.append(f'step {i + 1}: {mid} never arrived'); continue
        irt = _IDS.findall(m.get('In-Reply-To', '') or '')
        if expected_ids[i - 1] not in irt:
            problems.append(f'step {i + 1}: In-Reply-To is {irt or "ABSENT"}, '
                            f'expected {expected_ids[i - 1]}')
        refs = _IDS.findall(m.get('References', '') or '')
        if missing := [e for e in expected_ids[:i] if e not in refs]:
            problems.append(f'step {i + 1}: References is missing {missing} (has {refs or "ABSENT"})')
    return problems
