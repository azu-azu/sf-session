"""Windows スリープ防止ユーティリティ.

SetThreadExecutionState API でシステムのスリープを抑止する。
Ctrl+C で終了。
"""

import argparse
import ctypes
import logging
import sys
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# SetThreadExecutionState flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _set_execution_state(flags: int) -> None:
    """SetThreadExecutionState を呼ぶ."""
    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))  # type: ignore[attr-defined]


def stay_awake(minutes: int = 0, keep_display_on: bool = True) -> None:
    """スリープを防止する. Ctrl+C で停止."""
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    if keep_display_on:
        flags |= ES_DISPLAY_REQUIRED

    now_fmt = lambda: datetime.now().strftime("%H:%M:%S")  # noqa: E731

    if minutes > 0:
        end_time = datetime.now() + timedelta(minutes=minutes)
        logger.info(
            "StayAwake START (%d min) %s -> %s",
            minutes, now_fmt(), end_time.strftime("%H:%M:%S"),
        )
        try:
            while datetime.now() < end_time:
                _set_execution_state(flags)
                time.sleep(30)
        except KeyboardInterrupt:
            pass
    else:
        logger.info("StayAwake START (infinite) %s", now_fmt())
        try:
            while True:
                _set_execution_state(flags)
                time.sleep(30)
        except KeyboardInterrupt:
            pass

    _set_execution_state(ES_CONTINUOUS)
    logger.info("StayAwake STOP %s", now_fmt())


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Windows スリープ防止")
    parser.add_argument(
        "--minutes", type=int, default=0,
        help="持続時間(分)。0=無制限 (default: 0)",
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="ディスプレイ維持を無効にする",
    )
    args = parser.parse_args()

    stay_awake(minutes=args.minutes, keep_display_on=not args.no_display)
    return 0


if __name__ == "__main__":
    sys.exit(main())
