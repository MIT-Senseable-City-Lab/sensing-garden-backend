from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from composites import CompositeResult, ensure_results_composites
from trigger_handler import LocalStorageAdapter, S3StorageAdapter, StorageAdapter


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    storage = _storage(args.local_root)
    if args.command == "generate":
        results = ensure_results_composites(storage, args.bucket, args.results_key)
    else:
        results = _backfill(storage, args.bucket, args.prefix)
    print(json.dumps([_result_payload(result) for result in results], indent=2, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate missing black-background composite images.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--local-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--results-key", required=True)

    backfill = subparsers.add_parser("backfill")
    backfill.add_argument("--prefix", required=True)
    return parser


def _storage(local_root: Path | None) -> StorageAdapter:
    return LocalStorageAdapter(str(local_root)) if local_root else S3StorageAdapter()


def _backfill(storage: StorageAdapter, bucket: str, prefix: str) -> list[CompositeResult]:
    results: list[CompositeResult] = []
    for key in storage.list_keys(bucket, prefix, suffix="/results.json"):
        results.extend(ensure_results_composites(storage, bucket, key))
    return results


def _result_payload(result: CompositeResult) -> dict[str, object]:
    return result.model_dump(mode="json")


if __name__ == "__main__":
    raise SystemExit(main())
