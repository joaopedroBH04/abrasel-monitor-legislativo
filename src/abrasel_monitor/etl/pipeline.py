"""Pipeline ETL completo: Bronze -> Silver -> Gold.

Implementa a arquitetura Medallion conforme secao 7 do documento:
- Bronze: dados brutos imutaveis (JSON cru)
- Silver: dados normalizados e deduplicados (schema padronizado)
- Gold: dados enriquecidos com scoring e entidades (PostgreSQL)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from abrasel_monitor._shared.s3 import save_to_silver
from abrasel_monitor.collectors.base import ProposicaoRaw
from abrasel_monitor.models import (
    ExecucaoRobo,
    Parlamentar,
    Proposicao,
    Tramitacao,
)
from abrasel_monitor.scoring.engine import ScoringEngine

logger = structlog.get_logger()


class ETLPipeline:
    """Pipeline completo de processamento de dados legislativos."""

    def __init__(self, scoring_engine: ScoringEngine | None = None):
        self.scoring = scoring_engine or ScoringEngine()

    # ========================================================================
    # Silver Layer: Normalizacao
    # ========================================================================
    async def transform_to_silver(
        self,
        proposicoes_raw: list[ProposicaoRaw],
    ) -> list[dict[str, Any]]:
        """Transforma dados brutos em formato Silver normalizado.

        - Normaliza schemas divergentes entre fontes
        - Deduplicacao por chave composta (source + source_id)
        - Limpeza de textos (remocao de HTML, normalizacao)
        """
        seen: set[str] = set()
        silver_items: list[dict[str, Any]] = []

        for raw in proposicoes_raw:
            # Deduplicacao por chave composta
            key = f"{raw.source}:{raw.source_id}"
            if key in seen:
                continue
            seen.add(key)

            # Normalizacao
            item = raw.to_dict()
            item["ementa"] = self._clean_text(item.get("ementa"))
            item["ementa_detalhada"] = self._clean_text(item.get("ementa_detalhada"))

            silver_items.append(item)

        # Salvar na Silver layer
        if silver_items:
            source = silver_items[0].get("source", "unknown")
            await save_to_silver(source, "proposicoes", silver_items)

        logger.info("silver_transform_done", total_raw=len(proposicoes_raw), total_silver=len(silver_items))
        return silver_items

    def _clean_text(self, text: str | None) -> str | None:
        """Limpa texto: remove HTML, normaliza espacos."""
        if not text:
            return text
        # Remove tags HTML
        text = re.sub(r"<[^>]+>", " ", text)
        # Remove espacos multiplos
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # ========================================================================
    # Gold Layer: Enriquecimento e persistencia
    # ========================================================================
    async def load_to_gold(
        self,
        session: AsyncSession,
        silver_items: list[dict[str, Any]],
        aliados_ids: set[str] | None = None,
    ) -> dict[str, int]:
        """Carrega dados Silver no Gold layer (PostgreSQL) com scoring.

        Usa ON CONFLICT DO UPDATE para idempotencia (conforme RNF-09).
        """
        stats = {"inserted": 0, "updated": 0, "errors": 0}

        for item in silver_items:
            try:
                # Scoring
                scoring_result = self.scoring.score_proposicao(
                    ementa=item.get("ementa"),
                    ementa_detalhada=item.get("ementa_detalhada"),
                    temas=item.get("temas"),
                    autores_ids=[a.get("id") for a in item.get("autores", []) if isinstance(a, dict)],
                    aliados_ids=aliados_ids,
                )

                # Upsert (idempotente)
                stmt = insert(Proposicao).values(
                    source_id=item["source_id"],
                    source=item["source"],
                    tipo=item.get("tipo", ""),
                    numero=item.get("numero"),
                    ano=item.get("ano", 0),
                    ementa=item.get("ementa"),
                    ementa_detalhada=item.get("ementa_detalhada"),
                    keywords_matched=scoring_result.keywords_matched or None,
                    temas=scoring_result.temas_matched or None,
                    relevancia_score=scoring_result.score,
                    relevancia_nivel=scoring_result.nivel,
                    situacao_atual=item.get("situacao_atual"),
                    data_apresentacao=item.get("data_apresentacao"),
                    casa_origem=item.get("casa_origem"),
                    url_inteiro_teor=item.get("url_inteiro_teor"),
                    updated_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    constraint="uq_proposicao_source",
                    set_={
                        "ementa": item.get("ementa"),
                        "situacao_atual": item.get("situacao_atual"),
                        "relevancia_score": scoring_result.score,
                        "relevancia_nivel": scoring_result.nivel,
                        "keywords_matched": scoring_result.keywords_matched or None,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )

                result = await session.execute(stmt)
                if result.rowcount > 0:
                    stats["inserted"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.error("gold_load_error", source_id=item.get("source_id"), error=str(e))

        await session.commit()
        logger.info("gold_load_done", **stats)
        return stats

    async def load_parlamentar_to_gold(
        self,
        session: AsyncSession,
        parlamentar_data: dict[str, Any],
        source: str,
    ) -> None:
        """Carrega/atualiza parlamentar no Gold layer."""
        stmt = insert(Parlamentar).values(
            source_id=str(parlamentar_data.get("id", "")),
            source=source,
            nome_civil=parlamentar_data.get("nomeCivil", parlamentar_data.get("nome", "")),
            nome_parlamentar=parlamentar_data.get("nome", parlamentar_data.get("NomeParlamentar", "")),
            partido=parlamentar_data.get("siglaPartido", parlamentar_data.get("SiglaPartido")),
            uf=parlamentar_data.get("siglaUf", parlamentar_data.get("UfParlamentar")),
            legislatura_atual=parlamentar_data.get("idLegislatura"),
            foto_url=parlamentar_data.get("urlFoto", parlamentar_data.get("UrlFotoParlamentar")),
            email_oficial=parlamentar_data.get("email"),
            updated_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            constraint="uq_parlamentar_source",
            set_={
                "nome_parlamentar": parlamentar_data.get("nome", parlamentar_data.get("NomeParlamentar", "")),
                "partido": parlamentar_data.get("siglaPartido", parlamentar_data.get("SiglaPartido")),
                "uf": parlamentar_data.get("siglaUf", parlamentar_data.get("UfParlamentar")),
                "foto_url": parlamentar_data.get("urlFoto", parlamentar_data.get("UrlFotoParlamentar")),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await session.execute(stmt)

    # ========================================================================
    # Pipeline completo
    # ========================================================================
    async def run_full_pipeline(
        self,
        session: AsyncSession,
        proposicoes_raw: list[ProposicaoRaw],
        source: str,
        tipo_execucao: str = "incremental",
    ) -> dict[str, Any]:
        """Executa pipeline completo: Bronze (ja salvo) -> Silver -> Gold."""
        # Registrar execucao
        execucao = ExecucaoRobo(
            fonte=source,
            tipo_execucao=tipo_execucao,
        )
        session.add(execucao)
        await session.flush()

        try:
            # Silver
            silver_items = await self.transform_to_silver(proposicoes_raw)

            # Gold
            aliados_ids: set[str] = set()
            try:
                from abrasel_monitor.parlamentares.alignment import AlignmentEngine
                alignment = AlignmentEngine()
                aliados_ids = await alignment.get_aliados_ids(session)
            except Exception:
                pass

            gold_stats = await self.load_to_gold(session, silver_items, aliados_ids)

            # Atualizar execucao
            execucao.status = "success"
            execucao.total_coletado = len(silver_items)
            execucao.total_relevantes = sum(
                1 for item in silver_items
                if self.scoring.score_proposicao(item.get("ementa")).nivel in ("Alta", "Media")
            )
            execucao.fim = datetime.now(timezone.utc)

            await session.commit()

            return {
                "execucao_id": execucao.id,
                "source": source,
                "silver": {"total": len(silver_items)},
                "gold": gold_stats,
            }

        except Exception as e:
            execucao.status = "error"
            execucao.erro_mensagem = str(e)[:500]
            execucao.fim = datetime.now(timezone.utc)
            await session.commit()
            raise
