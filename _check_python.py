"""Check running Python version against pyproject.toml requires-python.

Runs *before* the package is installed, so it must not import anything
outside the standard library and must work on any Python 3.x.
"""

import re
import sys


def main():
    with open("pyproject.toml") as f:
        text = f.read()

    m = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text)
    if not m:
        print("[ERROR] requires-python not found in pyproject.toml")
        return 1

    req = (int(m.group(1)), int(m.group(2)))
    cur = sys.version_info[:2]

    if cur < req:
        print(
            "[ERROR] Python {}.{}+ required (current: {}.{})".format(
                req[0], req[1], cur[0], cur[1],
            )
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
