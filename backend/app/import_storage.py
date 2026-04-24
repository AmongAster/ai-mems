from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models import Meme
from .settings import settings


EXT_TO_CONTENT_TYPE: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@dataclass
class ImportResult:
    scanned: int
    created: int
    skipped_existing: int
    skipped_unsupported: int


def import_from_storage_dir(db: Session, storage_dir: Path) -> ImportResult:
    storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    scanned = created = skipped_existing = skipped_unsupported = 0

    for path in storage_dir.iterdir():
        if not path.is_file():
            continue
        scanned += 1

        ext = path.suffix.lower()
        content_type = EXT_TO_CONTENT_TYPE.get(ext)
        if not content_type:
            skipped_unsupported += 1
            continue

        existing = db.scalars(select(Meme).where(Meme.filename == path.name).limit(1)).first()
        if existing:
            skipped_existing += 1
            continue

        meme = Meme(
            caption=None,
            filename=path.name,
            content_type=content_type,
            source="import",
        )
        db.add(meme)
        created += 1

    if created:
        db.commit()

    return ImportResult(
        scanned=scanned,
        created=created,
        skipped_existing=skipped_existing,
        skipped_unsupported=skipped_unsupported,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import images from storage dir into SQLite memes table.")
    parser.add_argument(
        "--storage-dir",
        default=settings.storage_dir,
        help="Directory where images are stored (default: settings.STORAGE_DIR).",
    )
    args = parser.parse_args(argv)

    storage_dir = Path(args.storage_dir)
    with SessionLocal() as db:
        res = import_from_storage_dir(db, storage_dir)

    print(
        f"scanned={res.scanned} created={res.created} "
        f"skipped_existing={res.skipped_existing} skipped_unsupported={res.skipped_unsupported}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

