"""python -m sf_session.report_filter で実行。"""

from __future__ import annotations

import logging
import sys

from ..config import (
    DEFAULT_FILTER_OUTPUT,
    DEFAULT_IDS_FILE,
    PIPELINE_DIR,
    create_sf_client,
)
from ..utils import read_ids_file, setup_logging
from .job import run_report_filter_extract_job

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()

    try:
        ids = read_ids_file(DEFAULT_IDS_FILE)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    sf = create_sf_client()
    report_ids = sorted(ids)

    run_report_filter_extract_job(
        sf,
        report_ids,
        output_path=DEFAULT_FILTER_OUTPUT,
        pipeline_dir=PIPELINE_DIR,
    )


if __name__ == "__main__":
    main()
