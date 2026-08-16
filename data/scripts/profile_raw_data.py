"""Azure Blob canonical Raw의 API payload를 Blob 단위 스트리밍으로 프로파일링한다."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from storage import BlobStorage

RAW_RE = re.compile(
    r"^data-go-kr/(?P<dataset>[^/]+)/operation=(?P<operation>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/(?P<hash>[0-9a-f]{64})\.jsonl\.gz$"
)
DATE8_RE = re.compile(r"^\d{8}$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")


@dataclass
class FieldStats:
    present: int = 0
    null: int = 0
    empty: int = 0
    numeric: int = 0
    integer: int = 0
    date8: int = 0
    min_number: Decimal | None = None
    max_number: Decimal | None = None
    min_text: str | None = None
    max_text: str | None = None
    max_length: int = 0
    examples: list[str] = field(default_factory=list)
    unique_values: set[str] = field(default_factory=set)
    unique_capped: bool = False

    def observe(self, value: Any, *, unique_cap: int, example_cap: int) -> None:
        self.present += 1
        if value is None:
            self.null += 1
            return
        text = str(value).strip()
        self.max_length = max(self.max_length, len(text))
        if text == "":
            self.empty += 1
            return

        if len(self.examples) < example_cap and text not in self.examples:
            self.examples.append(text)
        if not self.unique_capped:
            self.unique_values.add(text)
            if len(self.unique_values) > unique_cap:
                self.unique_values.clear()
                self.unique_capped = True

        self.min_text = text if self.min_text is None else min(self.min_text, text)
        self.max_text = text if self.max_text is None else max(self.max_text, text)

        if DATE8_RE.fullmatch(text):
            try:
                datetime.strptime(text, "%Y%m%d")
            except ValueError:
                pass
            else:
                self.date8 += 1

        normalized = text.replace(",", "")
        try:
            number = Decimal(normalized)
        except InvalidOperation:
            return
        self.numeric += 1
        if INTEGER_RE.fullmatch(normalized):
            self.integer += 1
        self.min_number = number if self.min_number is None else min(self.min_number, number)
        self.max_number = number if self.max_number is None else max(self.max_number, number)

    def as_dict(self, rows: int) -> dict[str, Any]:
        nonempty = self.present - self.null - self.empty
        return {
            "present": self.present,
            "missing": rows - self.present,
            "null": self.null,
            "empty": self.empty,
            "nonempty": nonempty,
            "present_rate": round(self.present / rows, 6) if rows else 0.0,
            "null_or_empty_rate": round((self.null + self.empty) / rows, 6) if rows else 0.0,
            "numeric_rate_nonempty": round(self.numeric / nonempty, 6) if nonempty else 0.0,
            "integer_rate_nonempty": round(self.integer / nonempty, 6) if nonempty else 0.0,
            "yyyymmdd_rate_nonempty": round(self.date8 / nonempty, 6) if nonempty else 0.0,
            "unique_count": None if self.unique_capped else len(self.unique_values),
            "unique_count_capped": self.unique_capped,
            "max_length": self.max_length,
            "min_number": str(self.min_number) if self.min_number is not None else None,
            "max_number": str(self.max_number) if self.max_number is not None else None,
            "min_text": self.min_text,
            "max_text": self.max_text,
            "examples": self.examples,
        }


@dataclass
class OperationStats:
    rows: int = 0
    blobs: int = 0
    compressed_bytes: int = 0
    malformed_json_lines: int = 0
    invalid_payloads: int = 0
    basdt_missing: int = 0
    basdt_invalid: int = 0
    min_basdt: str | None = None
    max_basdt: str | None = None
    fields: dict[str, FieldStats] = field(default_factory=dict)
    month_rows: Counter[str] = field(default_factory=Counter)
    envelope_operation: Counter[str] = field(default_factory=Counter)
    envelope_source: Counter[str] = field(default_factory=Counter)
    legacy_present: int = 0
    payload_hash_present: int = 0

    def observe(self, envelope: dict[str, Any], *, unique_cap: int, example_cap: int) -> None:
        self.rows += 1
        self.envelope_operation[str(envelope.get("operation", ""))] += 1
        self.envelope_source[str(envelope.get("source", ""))] += 1
        self.legacy_present += int(envelope.get("legacy") is not None)
        self.payload_hash_present += int(bool(envelope.get("payloadHash")))

        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            self.invalid_payloads += 1
            return

        for name, value in payload.items():
            self.fields.setdefault(name, FieldStats()).observe(
                value,
                unique_cap=unique_cap,
                example_cap=example_cap,
            )

        bas_dt = payload.get("basDt")
        if bas_dt is None or not str(bas_dt).strip():
            self.basdt_missing += 1
            return
        text = str(bas_dt).strip()
        try:
            parsed = datetime.strptime(text, "%Y%m%d")
        except ValueError:
            self.basdt_invalid += 1
            return
        self.min_basdt = text if self.min_basdt is None else min(self.min_basdt, text)
        self.max_basdt = text if self.max_basdt is None else max(self.max_basdt, text)
        self.month_rows[parsed.strftime("%Y-%m")] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "blobs": self.blobs,
            "compressed_bytes": self.compressed_bytes,
            "malformed_json_lines": self.malformed_json_lines,
            "invalid_payloads": self.invalid_payloads,
            "basdt_missing": self.basdt_missing,
            "basdt_invalid": self.basdt_invalid,
            "min_basdt": self.min_basdt,
            "max_basdt": self.max_basdt,
            "month_rows": dict(sorted(self.month_rows.items())),
            "envelope": {
                "operation_values": dict(self.envelope_operation),
                "source_values": dict(self.envelope_source),
                "legacy_present": self.legacy_present,
                "payload_hash_present": self.payload_hash_present,
            },
            "payload_fields": {
                name: stats.as_dict(self.rows)
                for name, stats in sorted(self.fields.items())
            },
        }


def profile_dataset(
    storage: BlobStorage,
    *,
    container: str,
    dataset: str,
    unique_cap: int,
    example_cap: int,
) -> dict[str, Any]:
    prefix = f"data-go-kr/{dataset}/operation="
    client = storage.service_client.get_container_client(container)
    operations: dict[str, OperationStats] = {}
    invalid_paths: list[str] = []
    blobs = list(client.list_blobs(name_starts_with=prefix))

    for index, blob in enumerate(blobs, start=1):
        path = str(blob.name)
        match = RAW_RE.fullmatch(path)
        if not match or match.group("dataset") != dataset:
            invalid_paths.append(path)
            continue
        operation = match.group("operation")
        stats = operations.setdefault(operation, OperationStats())
        stats.blobs += 1
        stats.compressed_bytes += int(blob.size or 0)

        decoded = gzip.decompress(storage.download_bytes(container, path))
        for raw_line in decoded.splitlines():
            if not raw_line.strip():
                continue
            try:
                envelope = json.loads(raw_line)
            except json.JSONDecodeError:
                stats.malformed_json_lines += 1
                continue
            if not isinstance(envelope, dict):
                stats.malformed_json_lines += 1
                continue
            stats.observe(
                envelope,
                unique_cap=unique_cap,
                example_cap=example_cap,
            )

        if index % 25 == 0 or index == len(blobs):
            print(f"PROFILE PROGRESS dataset={dataset} blobs={index}/{len(blobs)}")

    operation_payload = {
        name: stats.as_dict() for name, stats in sorted(operations.items())
    }
    return {
        "dataset": dataset,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "container": container,
        "prefix": prefix,
        "total_rows": sum(item["rows"] for item in operation_payload.values()),
        "total_blobs": sum(item["blobs"] for item in operation_payload.values()),
        "compressed_bytes": sum(
            item["compressed_bytes"] for item in operation_payload.values()
        ),
        "invalid_paths": invalid_paths,
        "operations": operation_payload,
    }


def render_markdown(profile: dict[str, Any]) -> str:
    lines = [
        f"# Raw Payload Profile - {profile['dataset']}",
        "",
        f"- total_blobs: **{profile['total_blobs']:,}**",
        f"- total_rows: **{profile['total_rows']:,}**",
        f"- compressed_bytes: **{profile['compressed_bytes']:,}**",
        "",
        "| operation | blobs | rows | basDt | fields | invalid payload |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for operation, stats in profile["operations"].items():
        lines.append(
            f"| `{operation}` | {stats['blobs']:,} | {stats['rows']:,} | "
            f"{stats['min_basdt'] or '-'} ~ {stats['max_basdt'] or '-'} | "
            f"{len(stats['payload_fields'])} | {stats['invalid_payloads']:,} |"
        )

    for operation, stats in profile["operations"].items():
        lines += [
            "",
            f"## {operation}",
            "",
            "| field | present% | null/empty% | numeric% | date% | unique | examples |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for name, field_stats in stats["payload_fields"].items():
            unique = ">cap" if field_stats["unique_count_capped"] else str(field_stats["unique_count"])
            examples = ", ".join(
                str(value).replace("|", "\\|") for value in field_stats["examples"]
            )
            lines.append(
                f"| `{name}` | {field_stats['present_rate'] * 100:.2f} | "
                f"{field_stats['null_or_empty_rate'] * 100:.2f} | "
                f"{field_stats['numeric_rate_nonempty'] * 100:.2f} | "
                f"{field_stats['yyyymmdd_rate_nonempty'] * 100:.2f} | {unique} | {examples} |"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/raw-profile"))
    parser.add_argument("--unique-cap", type=int, default=20_000)
    parser.add_argument("--example-cap", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    if args.unique_cap <= 0 or args.example_cap <= 0:
        raise ValueError("caps must be positive")

    profile = profile_dataset(
        BlobStorage.from_env(),
        container=os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw"),
        dataset=args.dataset,
        unique_cap=args.unique_cap,
        example_cap=args.example_cap,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{args.dataset}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / f"{args.dataset}.md").write_text(
        render_markdown(profile),
        encoding="utf-8",
    )
    print(
        "PROFILE COMPLETE "
        f"dataset={profile['dataset']} blobs={profile['total_blobs']} "
        f"rows={profile['total_rows']} operations={len(profile['operations'])}"
    )


if __name__ == "__main__":
    main()
