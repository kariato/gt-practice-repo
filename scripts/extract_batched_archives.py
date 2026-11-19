"""Extract tar.gz email archives into folders of at most 1,000 files.

Example:
    python scripts/extract_batched_archives.py data/enron_mail_20150507.tar.gz

An archive named example.tar.gz produces data/example/. Original directory paths
are preserved, with batch_0001, batch_0002, ... inserted before each file name.
"""

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def archive_stem(path: Path) -> str:
    for suffix in (".tar.gz", ".tgz"):
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    raise ValueError(f"Expected a .tar.gz or .tgz archive: {path}")


def extract_batched(archive_path: Path, batch_size: int) -> tuple[Path, int]:
    archive_path = archive_path.resolve(strict=True)
    destination = archive_path.parent / archive_stem(archive_path)
    temporary = archive_path.parent / (destination.name + ".extracting")
    if destination.exists() or temporary.exists():
        raise FileExistsError(f"Output already exists: {destination} or {temporary}")

    temporary.mkdir()
    counts: dict[PurePosixPath, int] = defaultdict(int)
    created_batches: set[Path] = set()
    total = 0
    try:
        with tarfile.open(archive_path, "r|gz") as archive:
            for member in archive:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Unsupported archive entry: {member.name}")

                relative = PurePosixPath(member.name)
                if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
                    raise ValueError(f"Unsafe archive path: {member.name}")

                parent = relative.parent
                batch_number = counts[parent] // batch_size + 1
                batch_dir = temporary.joinpath(*parent.parts, f"batch_{batch_number:04d}")
                if batch_dir not in created_batches:
                    batch_dir.mkdir(parents=True, exist_ok=True)
                    created_batches.add(batch_dir)
                target = batch_dir / relative.name
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"Could not read archive entry: {member.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

                counts[parent] += 1
                total += 1
                if total % 100_000 == 0:
                    print(f"{archive_path.name}: {total:,} emails extracted", flush=True)

        manifest = {
            "archive": archive_path.name,
            "email_files": total,
            "original_folders": len(counts),
            "maximum_files_per_batch": batch_size,
            "layout": "Original archive paths with batch_0001, batch_0002, ... before filenames",
        }
        (temporary / "EXTRACTION.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.rename(temporary, destination)
        return destination, total
    except Exception:
        print(f"Incomplete extraction remains at {temporary}", flush=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path, help=".tar.gz or .tgz archives")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    for archive in args.archives:
        destination, count = extract_batched(archive, args.batch_size)
        print(f"Done: {count:,} emails in {destination}", flush=True)


if __name__ == "__main__":
    main()
