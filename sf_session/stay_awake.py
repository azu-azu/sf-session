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

_KEEPALIVE_INTERVAL = 30  # seconds: SetThreadExecutionState refresh 間隔


def _set_execution_state(flags: int) -> None:
    """SetThreadExecutionState を呼ぶ."""
    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))  # type: ignore[attr-defined]


def stay_awake(minutes: int = 0, keep_display_on: bool = True) -> None:
    """スリープを防止する. Ctrl+C で停止."""
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    if keep_display_on:
        flags |= ES_DISPLAY_REQUIRED

    def today_fmt() -> str:
        return datetime.now().strftime("%Y/%m/%d (%a)")

    def now_fmt() -> str:
        return datetime.now().strftime("%H:%M:%S")

    end_time = (datetime.now() + timedelta(minutes=minutes)) if minutes > 0 else None

    if end_time is not None:
        logger.info(
            "StayAwake START (%d min) %s -> %s",
            minutes, now_fmt(), end_time.strftime("%H:%M:%S"),
        )
    else:
        logger.info("%s", today_fmt())
        logger.info("--------------------------")
        logger.info("StayAwake - infinite -")
        logger.info("--------------------------")

    try:
        while end_time is None or datetime.now() < end_time:
            _set_execution_state(flags)
            time.sleep(_KEEPALIVE_INTERVAL)
    except KeyboardInterrupt:
        pass

    _set_execution_state(ES_CONTINUOUS)
    logger.info("StayAwake STOP %s", now_fmt())


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
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
