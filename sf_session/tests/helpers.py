"""テスト共通ヘルパー。"""

from __future__ import annotations

from sf_session.macro_book_reader import JobEntry


def make_job(**kwargs) -> JobEntry:
    """テスト用 JobEntry factory。"""
    defaults = dict(
        no="1",
        report_id="00O123",
        has_filename=False,
        new_filename="",
        src_folder_name="/tmp/dest",
        encode="UTF-8",
        skip="",
    )
    defaults.update(kwargs)
    return JobEntry(**defaults)
