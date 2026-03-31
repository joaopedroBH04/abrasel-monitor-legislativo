"""Classe base para todos os coletores legislativos.

Segue o padrao de adaptadores do mcp-brasil: cada coletor e independente
mas entrega dados no mesmo schema interno padronizado.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from typing import Any

import structlog

from abrasel_monitor._shared.checkpoint import CheckpointManager
from abrasel_monitor._shared.http_client import MonitorHTTPClient
from abrasel_monitor._shared.s3 import save_to_bronze

logger = structlog.get_logger()


class ProposicaoRaw:
    """Schema interno padronizado para proposicoes de qualquer fonte."""

    def __init__(
        self,
        source_id: str,
        source: str,
        tipo: str,
        numero: int | None,
        ano: int,
        ementa: str | None,
        ementa_detalhada: str | None = None,
        situacao_atual: str | None = None,
        data_apresentacao: str | None = None,
        casa_origem: str | None = None,
        url_inteiro_teor: str | None = None,
        autores: list[dict[str, Any]] | None = None,
        temas: list[dict[str, Any]] | None = None,
        raw_data: dict[str, Any] | None = None,
    ):
        self.source_id = source_id
        self.source = source
        self.tipo = tipo
        self.numero = numero
        self.ano = ano
        self.ementa = ementa
        self.ementa_detalhada = ementa_detalhada
        self.situacao_atual = situacao_atual
        self.data_apresentacao = data_apresentacao
        self.casa_origem = casa_origem
        self.url_inteiro_teor = url_inteiro_teor
        self.autores = autores or []
        self.temas = temas or []
        self.raw_data = raw_data or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source": self.source,
            "tipo": self.tipo,
            "numero": self.numero,
            "ano": self.ano,
            "ementa": self.ementa,
            "ementa_detalhada": self.ementa_detalhada,
            "situacao_atual": self.situacao_atual,
            "data_apresentacao": self.data_apresentacao,
            "casa_origem": self.casa_origem,
            "url_inteiro_teor": self.url_inteiro_teor,
            "autores": self.autores,
            "temas": self.temas,
        }


class BaseCollector(abc.ABC):
    """Interface base que todos os coletores devem implementar."""

    source_name: str = ""

    def __init__(self, client: MonitorHTTPClient):
        self.client = client
        self.checkpoint = CheckpointManager(self.source_name)
        self._stats = {"total_coletado": 0, "erros": 0}

    @abc.abstractmethod
    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        """Coleta proposicoes por periodo."""
        ...

    @abc.abstractmethod
    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta historico de tramitacao de uma proposicao."""
        ...

    @abc.abstractmethod
    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta votacoes nominais de uma proposicao."""
        ...

    @abc.abstractmethod
    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        """Coleta lista de parlamentares."""
        ...

    @abc.abstractmethod
    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        """Coleta pauta de plenario e comissoes."""
        ...

    async def collect_discursos(self, parlamentar_id: str, data_inicio: str | None = None) -> list[dict[str, Any]]:
        """Coleta discursos de um parlamentar. Implementacao opcional."""
        return []

    async def save_raw(self, data_type: str, data: Any) -> str:
        """Salva dados brutos na camada Bronze."""
        return await save_to_bronze(self.source_name, data_type, data)

    async def run_full_load(self, ano_inicio: int = 1988) -> dict[str, int]:
        """Executa carga historica completa desde o ano especificado."""
        current_year = datetime.now(timezone.utc).year
        logger.info("full_load_start", source=self.source_name, ano_inicio=ano_inicio, ano_fim=current_year)

        all_proposicoes: list[ProposicaoRaw] = []

        for ano in range(ano_inicio, current_year + 1):
            checkpoint_data = await self.checkpoint.load(f"full_load_{ano}")
            if checkpoint_data and checkpoint_data.get("completed"):
                logger.info("full_load_skip_year", source=self.source_name, ano=ano, reason="checkpoint_exists")
                continue

            try:
                proposicoes = await self.collect_proposicoes(ano_inicio=ano, ano_fim=ano)
                all_proposicoes.extend(proposicoes)
                await self.save_raw("proposicoes", [p.to_dict() for p in proposicoes])
                await self.checkpoint.save(f"full_load_{ano}", {"completed": True, "count": len(proposicoes)})
                self._stats["total_coletado"] += len(proposicoes)
                logger.info("full_load_year_done", source=self.source_name, ano=ano, count=len(proposicoes))
            except Exception as e:
                self._stats["erros"] += 1
                logger.error("full_load_year_error", source=self.source_name, ano=ano, error=str(e))

        return self._stats

    async def run_incremental(self, desde: str | None = None) -> dict[str, int]:
        """Executa coleta incremental desde a ultima execucao."""
        current_year = datetime.now(timezone.utc).year
        logger.info("incremental_start", source=self.source_name)

        proposicoes = await self.collect_proposicoes(ano_inicio=current_year)
        await self.save_raw("proposicoes_incremental", [p.to_dict() for p in proposicoes])
        self._stats["total_coletado"] = len(proposicoes)

        return self._stats
