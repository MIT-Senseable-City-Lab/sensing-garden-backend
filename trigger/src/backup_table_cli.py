"""CLI to back up a DynamoDB table to S3 before a Terraform removal.

Scans the whole table and writes newline-delimited JSON (one item per line,
gzip-compressed) to the output bucket. Deliberately writes OUTSIDE the v1/ and
v2/ prefixes the S3 trigger watches (see terraform/lambda.tf notification
filters) -- a backup dump is exactly the kind of bulk multi-object write that
caused the composite-generation recursion, and this is a single object, but
keeping it structurally outside the watched prefixes means it can never
matter regardless of how the filters evolve.

Usage:
    poetry run python -m backup_table_cli --table sensing-garden-detections \
        --bucket scl-sensing-garden --prefix backups/dynamodb

Writes: s3://<bucket>/<prefix>/<table>/<UTC timestamp>.jsonl.gz
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterator, Sequence

import boto3


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Preserve int vs float the way the item actually stored it.
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def scan_all_items(table_name: str) -> Iterator[Dict[str, Any]]:
    table = boto3.resource("dynamodb").Table(table_name)
    kwargs: Dict[str, Any] = {}
    while True:
        response = table.scan(**kwargs)
        yield from response.get("Items", [])
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return
        kwargs["ExclusiveStartKey"] = last_key


def backup_table(table_name: str, bucket: str, prefix: str, *, dry_run: bool = False) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{prefix.rstrip('/')}/{table_name}/{timestamp}.jsonl.gz"

    buffer = io.BytesIO()
    count = 0
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        for item in scan_all_items(table_name):
            gz.write((json.dumps(item, default=_json_default) + "\n").encode("utf-8"))
            count += 1

    size_bytes = buffer.tell()
    if not dry_run:
        buffer.seek(0)
        boto3.client("s3").put_object(
            Bucket=bucket, Key=key, Body=buffer.getvalue(), ContentType="application/gzip"
        )

    return {
        "table": table_name,
        "bucket": bucket,
        "key": key,
        "item_count": count,
        "compressed_bytes": size_bytes,
        "dry_run": dry_run,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, help="DynamoDB table name to back up")
    parser.add_argument("--bucket", required=True, help="S3 bucket to write the backup to")
    parser.add_argument(
        "--prefix",
        default="backups/dynamodb",
        help="S3 key prefix, kept outside v1/ and v2/ so the trigger never sees it (default: backups/dynamodb)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan and report counts without writing to S3")
    args = parser.parse_args(argv)

    if args.prefix.startswith("v1/") or args.prefix.startswith("v2/"):
        parser.error("--prefix must stay outside v1/ and v2/ (the trigger-watched prefixes)")

    result = backup_table(args.table, args.bucket, args.prefix, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
