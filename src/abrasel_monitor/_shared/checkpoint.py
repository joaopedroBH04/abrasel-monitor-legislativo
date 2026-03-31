"""Sistema de checkpoint para retomada de coleta em caso de falha.

Salva progresso no DynamoDB (producao) ou arquivo local (desenvolvimento).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

CHECKPOINT_DIR = Path("data/checkpoints")


class CheckpointManager:
    """Gerencia checkpoints de progresso para coleta incremental e historica."""

    def __init__(self, source: str, use_dynamodb: bool = False):
        self.source = source
        self.use_dynamodb = use_dynamodb
        self._local_dir = CHECKPOINT_DIR / source
        self._local_dir.mkdir(parents=True, exist_ok=True)

    def _local_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace(":", "_")
        return self._local_dir / f"{safe_key}.json"

    async def save(self, key: str, data: dict[str, Any]) -> None:
        checkpoint = {
            "source": self.source,
            "key": key,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.use_dynamodb:
            await self._save_dynamodb(key, checkpoint)
        else:
            self._save_local(key, checkpoint)

        logger.info("checkpoint_saved", source=self.source, key=key)

    async def load(self, key: str) -> dict[str, Any] | None:
        if self.use_dynamodb:
            return await self._load_dynamodb(key)
        return self._load_local(key)

    def _save_local(self, key: str, checkpoint: dict[str, Any]) -> None:
        path = self._local_path(key)
        path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_local(self, key: str) -> dict[str, Any] | None:
        path = self._local_path(key)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("data")

    async def _save_dynamodb(self, key: str, checkpoint: dict[str, Any]) -> None:
        import boto3
        from abrasel_monitor.settings import settings

        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamodb_table_checkpoints)
        table.put_item(Item={
            "source": self.source,
            "checkpoint_key": key,
            "data": json.dumps(checkpoint["data"]),
            "updated_at": checkpoint["updated_at"],
        })

    async def _load_dynamodb(self, key: str) -> dict[str, Any] | None:
        import boto3
        from abrasel_monitor.settings import settings

        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamodb_table_checkpoints)
        response = table.get_item(Key={"source": self.source, "checkpoint_key": key})
        item = response.get("Item")
        if not item:
            return None
        return json.loads(item["data"])
