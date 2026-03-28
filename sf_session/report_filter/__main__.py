"""python -m sf_session.report_filter で実行。"""

from __future__ import annotations

import argparse
import logging
import sys

from ..config import PIPELINES, VALID_PIPELINES, create_sf_client
from ..macro_book_reader import read_jobs
from ..utils import setup_logging
from .job import run_report_probe_job

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Salesforce レポートの probe（行数・列数・名前取得 → Excel 出力）",
    )
    parser.add_argument(
        "pipeline",
        choices=VALID_PIPELINES,
        help="実行対象の pipeline 名",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    args = parse_args(argv)

    pipeline = PIPELINES[args.pipeline]

    try:
        jobs = read_jobs(pipeline.macro_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    report_ids = sorted({j.report_id for j in jobs if j.report_id})
    logger.info("対象レポート: %d 件", len(report_ids))

    sf = create_sf_client()
    run_report_probe_job(sf, report_ids, result_dir=pipeline.result_dir)


if __name__ == "__main__":
    main()
