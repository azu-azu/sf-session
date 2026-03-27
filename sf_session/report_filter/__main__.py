"""python -m sf_session.report_filter で実行。"""

from __future__ import annotations

import logging
import sys

from ..config import PIPELINES, create_sf_client
from ..macro_book_reader import read_jobs
from ..utils import setup_logging
from .job import run_report_probe_job

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()

    pipeline = PIPELINES["archive"]

    try:
        jobs = read_jobs(pipeline.macro_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    report_ids = sorted({j.report_id for j in jobs if j.report_id})
    logger.info("対象レポート: %d 件", len(report_ids))

    sf = create_sf_client()
    run_report_probe_job(sf, report_ids)


if __name__ == "__main__":
    main()
