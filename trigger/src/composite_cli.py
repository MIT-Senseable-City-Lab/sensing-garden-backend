from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from composite_repair import (
    DynamoTrackStore,
    RepairManifest,
    apply_repair_manifest,
    backfill_dynamo_prefix,
    build_repair_manifest,
)
from composites import CompositeResult, ensure_results_composites
from trigger_handler import LocalStorageAdapter, S3StorageAdapter, StorageAdapter


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    storage = _storage(args.local_root)
    if args.command == "generate":
        results = ensure_results_composites(storage, args.bucket, args.results_key, args.overwrite_existing)
        print(json.dumps([_result_payload(result) for result in results], indent=2, sort_keys=True))
    elif args.command == "backfill":
        results = _backfill(storage, args.bucket, args.prefix, args.overwrite_existing)
        print(json.dumps([_result_payload(result) for result in results], indent=2, sort_keys=True))
    elif args.command == "backfill-dynamo-prefix":
        results = backfill_dynamo_prefix(
            storage,
            DynamoTrackStore(),
            args.bucket,
            args.prefix,
            args.overwrite_existing,
        )
        print(json.dumps([result.model_dump(mode="json") for result in results], indent=2, sort_keys=True))
    elif args.command == "repair-plan":
        manifest = build_repair_manifest(storage, DynamoTrackStore(), args.bucket, args.results_key)
        print(manifest.model_dump_json(indent=2))
    else:
        manifest = RepairManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        results = apply_repair_manifest(DynamoTrackStore(), manifest)
        print(json.dumps([result.model_dump(mode="json") for result in results], indent=2, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate missing black-background composite images.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--local-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--results-key", required=True)
    generate.add_argument("--overwrite-existing", action="store_true")

    backfill = subparsers.add_parser("backfill")
    backfill.add_argument("--prefix", required=True)
    backfill.add_argument("--overwrite-existing", action="store_true")

    backfill_dynamo = subparsers.add_parser("backfill-dynamo-prefix")
    backfill_dynamo.add_argument("--prefix", required=True)
    backfill_dynamo.add_argument("--overwrite-existing", action="store_true")

    repair_plan = subparsers.add_parser("repair-plan")
    repair_plan.add_argument("--results-key", required=True)

    repair_apply = subparsers.add_parser("repair-apply")
    repair_apply.add_argument("--manifest", type=Path, required=True)
    return parser


def _storage(local_root: Path | None) -> StorageAdapter:
    return LocalStorageAdapter(str(local_root)) if local_root else S3StorageAdapter()


def _backfill(
    storage: StorageAdapter,
    bucket: str,
    prefix: str,
    overwrite_existing: bool,
) -> list[CompositeResult]:
    results: list[CompositeResult] = []
    for key in storage.list_keys(bucket, prefix, suffix="/results.json"):
        results.extend(ensure_results_composites(storage, bucket, key, overwrite_existing))
    return results


def _result_payload(result: CompositeResult) -> dict[str, object]:
    return result.model_dump(mode="json")


if __name__ == "__main__":
    raise SystemExit(main())
