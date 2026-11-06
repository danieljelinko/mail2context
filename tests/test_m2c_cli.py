import os, subprocess, sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def run_m2c(tmp_path) -> Callable[..., subprocess.CompletedProcess]:
    "Factory: run scripts/m2c.py with an account that points at a closed loopback port."
    env = {**os.environ, 'PROTON_IMAP_HOST': '127.0.0.1', 'PROTON_IMAP_PORT': '1', 'PROTON_IMAP_TLS': 'none',
           'PROTON_USER': 'dj@ai4hu.org', 'PROTON_PASS': 'x'}            # port 1: any connect is refused
    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'm2c.py'), *args],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False)
    return _run


@pytest.fixture
def shots(tmp_path) -> Path:
    "A folder of two numbered screenshots plus a body file beside it."
    d = tmp_path / 'shots'; d.mkdir()
    (d / '02_b.png').write_bytes(b'b' * 2048); (d / '01_a.png').write_bytes(b'a' * 1024)
    (tmp_path / 'body.md').write_text('Bonjour,\n\nVoici les captures.\n')
    return d


def test_compose_dry_run_lists_attachments_in_order_without_connecting(run_m2c, shots):
    # Given a folder of screenshots and an account no connection can reach
    # When we preview a compose with the folder attached
    r = run_m2c('compose', '--to', 'dj@ai4hu.org', '--subject', 'S', '--file', 'body.md',
                '--attach', str(shots), '--dry-run')

    # Then it succeeds and lists each file, in name order, with the total
    assert r.returncode == 0, r.stderr
    assert r.stdout.index('01_a.png (1.0 KB)') < r.stdout.index('02_b.png (2.0 KB)')
    assert 'attached: 2 files, 3.0 KB' in r.stdout


def test_compose_accepts_attach_repeated(run_m2c, shots):
    # Given two files named one by one
    # When --attach is repeated
    r = run_m2c('compose', '--to', 'a@x', '--subject', 'S', '--file', 'body.md',
                '--attach', str(shots / '02_b.png'), '--attach', str(shots / '01_a.png'), '--dry-run')

    # Then both are listed, in the order given
    assert r.stdout.index('02_b.png') < r.stdout.index('01_a.png')


def test_compose_refuses_a_missing_attachment_before_connecting(run_m2c, shots):
    # Given an attachment path that does not exist
    # When we compose for real (not a dry run)
    r = run_m2c('compose', '--to', 'a@x', '--subject', 'S', '--file', 'body.md', '--attach', 'nope.png')

    # Then it stops on the missing file, never reaching the (refused) connection
    assert r.returncode != 0
    assert 'attachment not found: nope.png' in r.stderr
    assert 'ConnectionRefused' not in r.stderr


def test_draft_refuses_a_missing_attachment_before_connecting(run_m2c, shots):
    # Given a reply draft with an attachment path that does not exist
    # When we run it
    r = run_m2c('draft', 'abcd1234', '--file', 'body.md', '--attach', 'nope.png', '--dry-run')

    # Then the missing file is reported before the thread is fetched
    assert r.returncode != 0
    assert 'attachment not found: nope.png' in r.stderr
    assert 'ConnectionRefused' not in r.stderr
