"""Utilidades para persistencia no S3 (Bronze e Silver layers)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from abrasel_monitor.settings import settings

logger = structlog.get_logger()


def _build_s3_path(source: str, data_type: str, date: datetime | None = None) -> str:
    """Gera path particionado: fonte/tipo/ano/mes/dia/timestamp.json"""
    dt = date or datetime.now(timezone.utc)
    return f"{source}/{data_type}/ano={dt.year}/mes={dt.month:02d}/dia={dt.day:02d}/{dt.strftime('%Y%m%dT%H%M%S')}.json"


async def save_to_bronze(
    source: str,
    data_type: str,
    data: dict[str, Any] | list[Any],
    date: datetime | None = None,
    use_local: bool = True,
) -> str:
    """Salva dados brutos na camada Bronze (S3 ou local)."""
    path = _build_s3_path(source, data_type, date)

    if use_local:
        return _save_local("data/bronze", path, data)

    return await _save_s3(settings.s3_bucket_bronze, path, data)


async def save_to_silver(
    source: str,
    data_type: str,
    data: dict[str, Any] | list[Any],
    date: datetime | None = None,
    use_local: bool = True,
) -> str:
    """Salva dados normalizados na camada Silver."""
    path = _build_s3_path(source, data_type, date)

    if use_local:
        return _save_local("data/silver", path, data)

    return await _save_s3(settings.s3_bucket_silver, path, data)


def _save_local(base_dir: str, path: str, data: dict[str, Any] | list[Any]) -> str:
    from pathlib import Path

    full_path = Path(base_dir) / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("bronze_saved_local", path=str(full_path))
    return str(full_path)


async def _save_s3(bucket: str, path: str, data: dict[str, Any] | list[Any]) -> str:
    import boto3

    s3 = boto3.client("s3", region_name=settings.aws_region)
    body = json.dumps(data, ensure_ascii=False, default=str)
    s3.put_object(Bucket=bucket, Key=path, Body=body.encode("utf-8"), ContentType="application/json")
    s3_path = f"s3://{bucket}/{path}"
    logger.info("bronze_saved_s3", path=s3_path)
    return s3_path
