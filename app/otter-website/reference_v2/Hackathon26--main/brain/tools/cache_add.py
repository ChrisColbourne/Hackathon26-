"""Promote a recording into the demo cache.

  python -m brain.tools.cache_add --list            # recent recordings with their verdicts
  python -m brain.tools.cache_add 143022_117        # copy that stamp into brain/demo_cache/
  python -m brain.tools.cache_add 143022_117 --name quotient_mistake
"""

from __future__ import annotations

import argparse
import sys

from .. import config
from ..demo_cache import add_from_recording
from ..schemas import BoardAnalysis


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stamp", nargs="?", help="recording stamp, e.g. 143022_117")
    p.add_argument("--name", help="file name to use in the cache")
    p.add_argument("--list", action="store_true", help="show the last 15 recordings")
    a = p.parse_args(argv)

    if a.list or not a.stamp:
        files = sorted(config.RECORD_DIR.glob("*.json"))[-15:]
        if not files:
            print(f"no recordings in {config.RECORD_DIR}")
            return 1
        for f in files:
            try:
                an = BoardAnalysis.model_validate_json(f.read_text())
                fe = an.first_error
                print(f"{f.stem}  conf={an.confidence:.2f}  {an.topic:<10} "
                      f"{('L%d %s' % (fe.line, fe.status.value)) if fe else 'ok':<16} {an.problem[:40]}")
            except Exception as e:
                print(f"{f.stem}  (unreadable: {e})")
        return 0

    out = add_from_recording(a.stamp, name=a.name)
    print(f"cached -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
