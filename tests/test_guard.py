from pathlib import Path

from mail2context.guard import describe_guard


def test_describe_guard_reports_direct_mode_when_no_level_file_exists(tmp_path: Path):
    # Given no guard installed
    # When described
    # Then the tool says so plainly rather than failing
    assert describe_guard(tmp_path / 'level') == 'guard not installed — direct mode'


def test_describe_guard_reports_the_level_file_verbatim(tmp_path: Path):
    # Given an installed guard at level 3 with an expiry
    p = tmp_path / 'level'; p.write_text('3 until 2026-09-17T18:00:00+00:00\n')

    # When described
    # Then the level and expiry are shown as the guard wrote them
    assert describe_guard(p) == 'guard level 3 until 2026-09-17T18:00:00+00:00'
