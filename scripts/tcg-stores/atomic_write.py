"""Write a JSON file atomically.

A plain ``json.dump(fh)`` leaves a truncated, unparseable file if the
process is killed mid-write. Every stage of a data pipeline then reads
that file as if it were complete, and the failure surfaces much later
as a mystery - a missing key, a short list, a wrong count.

Writing to a sibling temporary file and renaming it into place means
the destination is either the old file or the new one, never a
half-written mixture. The rename is atomic on the same filesystem.
"""

import json
import os
from pathlib import Path


def write_json_atomic(path, obj, indent=1, separators=None):
    """Write obj as JSON to path, atomically.

    indent=None reproduces json.dump's own default output (no
    indentation, ", " and ": " separators) - the format the earlier
    version of the pipeline produced for its large geojson files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            if indent is None:
                json.dump(obj, fh, ensure_ascii=False)
            elif separators is None:
                json.dump(obj, fh, ensure_ascii=False, indent=indent)
            else:
                json.dump(obj, fh, ensure_ascii=False, separators=separators)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    finally:
        # If the write failed, do not leave the temporary file behind.
        # A SIGKILL cannot run this block, so a stale .tmp may survive a
        # hard kill - it is never read, and the next write reuses the
        # same name, overwriting it.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path
