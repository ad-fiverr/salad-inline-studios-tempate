#!/opt/venv/bin/python

import sys
from pathlib import Path


if len(sys.argv) not in (1, 2):
    raise SystemExit("Usage: salad-patch-inline-models.py [path-to-exact-1.3.26-models.py]")
SOURCE = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("/opt/inline-studio/core/src/inline_core/studio/models.py")


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise SystemExit(f"Expected one upstream {label} block, found {count}; refusing to patch.")
    return source.replace(before, after, 1)


source = SOURCE.read_text(encoding="utf-8")
if "_snapshot_download_max_workers" in source:
    raise SystemExit("The model downloader already contains the Salad worker cap; refusing to patch twice.")

source = replace_once(
    source,
    "import logging\nimport shutil\nimport threading\n",
    "import logging\nimport os\nimport shutil\nimport threading\n",
    "import block",
)

source = replace_once(
    source,
    'logger = logging.getLogger("inline_core.studio.models")\n',
    '''logger = logging.getLogger("inline_core.studio.models")


def _snapshot_download_max_workers() -> int:
    """Bound only this model downloader's Hugging Face file worker pool."""
    raw_value = os.environ.get("INLINE_HF_SNAPSHOT_MAX_WORKERS", "2")
    try:
        workers = int(raw_value)
    except ValueError:
        logger.warning("Invalid INLINE_HF_SNAPSHOT_MAX_WORKERS=%r; using 2.", raw_value)
        return 2
    if not 1 <= workers <= 8:
        logger.warning("INLINE_HF_SNAPSHOT_MAX_WORKERS=%r is outside 1..8; using 2.", raw_value)
        return 2
    return workers
''',
    "logger block",
)

source = replace_once(
    source,
    '''snapshot_download(
                        comp.repo,
                        allow_patterns=list(wanted),
                        local_dir=str(staging),
                        token=token,
                        tqdm_class=tqdm_class,
                    )''',
    '''snapshot_download(
                        comp.repo,
                        allow_patterns=list(wanted),
                        local_dir=str(staging),
                        max_workers=_snapshot_download_max_workers(),
                        token=token,
                        tqdm_class=tqdm_class,
                    )''',
    "allow-patterns snapshot_download call",
)

source = replace_once(
    source,
    '''root = snapshot_download(
                    comp.repo,
                    allow_patterns=f"{folder}/*",
                    local_dir=str(staging),
                    token=token,
                    tqdm_class=tqdm_class,
                )''',
    '''root = snapshot_download(
                    comp.repo,
                    allow_patterns=f"{folder}/*",
                    local_dir=str(staging),
                    max_workers=_snapshot_download_max_workers(),
                    token=token,
                    tqdm_class=tqdm_class,
                )''',
    "folder snapshot_download call",
)

if source.count("max_workers=_snapshot_download_max_workers()") != 2:
    raise SystemExit("Patched model downloader did not contain exactly two bounded snapshot calls.")

SOURCE.write_text(source, encoding="utf-8")
print("Applied Salad's bounded max_workers setting to the two Inline Studio model snapshot downloads.")
