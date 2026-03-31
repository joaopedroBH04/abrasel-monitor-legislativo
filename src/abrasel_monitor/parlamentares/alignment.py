"""Motor de Calculo do Indice de Alinhamento Parlamentar.

Conforme secao 11 do documento:
- Indice = (Votos Favoraveis ao Setor / Total Votacoes de Interesse) x 100
- >= 70% = Aliado Forte
- 50-69% = Aliado
- 30-49% = Neutro
- < 30% = Opositor

Considerar apenas votacoes em proposicoes com score >= 3 (conforme 11.2).
Historico imutavel de votos por ID; snapshot do partido na data do voto.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from abrasel_monitor.models import (
    Parlamentar,
    VotoParlamentar,
    VotacaoNominal,
    Proposicao,
)

logger = structlog.get_logger()


@dataclass
class AlinhamentoResult:
    """Resultado do calculo de alinhamento de um parlamentar."""

    parlamentar_id: int
    total_votos_setor: int
    votos_favor_setor: int
    votos_contra_setor: int
    indice_alinhamento: Decimal
    classificacao: str


class AlignmentEngine:
    """Calcula e atualiza indice de alinhamento de parlamentares."""

    # Limiares de classificacao conforme secao 11.2
    THRESHOLD_ALIADO_FORTE = 70
    THRESHOLD_ALIADO = 50
    THRESHOLD_NEUTRO = 30

    # Score minimo da proposicao para considerar na votacao
    MIN_PROPOSICAO_SCORE = 3

    def classify(self, indice: float) -> str:
        """Classifica parlamentar baseado no indice de alinhamento."""
        if indice >= self.THRESHOLD_ALIADO_FORTE:
            return "Aliado Forte"
        elif indice >= self.THRESHOLD_ALIADO:
            return "Aliado"
        elif indice >= self.THRESHOLD_NEUTRO:
            return "Neutro"
        return "Opositor"

    async def calculate_alignment(
        self,
        session: AsyncSession,
        parlamentar_id: int,
    ) -> AlinhamentoResult:
        """Calcula indice de alinhamento de um parlamentar."""
        # Buscar votos em proposicoes relevantes (score >= 3)
        stmt = (
            select(VotoParlamentar)
            .join(VotacaoNominal, VotoParlamentar.votacao_id == VotacaoNominal.id)
            .join(Proposicao, VotacaoNominal.proposicao_id == Proposicao.id)
            .where(
                VotoParlamentar.parlamentar_id == parlamentar_id,
                Proposicao.relevancia_score >= self.MIN_PROPOSICAO_SCORE,
            )
        )

        result = await session.execute(stmt)
        votos = result.scalars().all()

        total = len(votos)
        favor = sum(1 for v in votos if v.voto in ("Sim", "sim", "SIM"))
        contra = sum(1 for v in votos if v.voto in ("Nao", "nao", "NAO", "Não"))

        indice = Decimal(str(round((favor / total * 100), 2))) if total > 0 else Decimal("0")
        classificacao = self.classify(float(indice))

        return AlinhamentoResult(
            parlamentar_id=parlamentar_id,
            total_votos_setor=total,
            votos_favor_setor=favor,
            votos_contra_setor=contra,
            indice_alinhamento=indice,
            classificacao=classificacao,
        )

    async def update_all_alignments(self, session: AsyncSession) -> dict[str, int]:
        """Recalcula indice de alinhamento de todos os parlamentares."""
        stmt = select(Parlamentar.id)
        result = await session.execute(stmt)
        parlamentar_ids = result.scalars().all()

        stats = {"total": 0, "aliado_forte": 0, "aliado": 0, "neutro": 0, "opositor": 0}

        for pid in parlamentar_ids:
            alignment = await self.calculate_alignment(session, pid)

            # Atualizar no banco
            parlamentar = await session.get(Parlamentar, pid)
            if parlamentar:
                parlamentar.total_votos_setor = alignment.total_votos_setor
                parlamentar.votos_favor_setor = alignment.votos_favor_setor
                parlamentar.indice_alinhamento = alignment.indice_alinhamento
                parlamentar.classificacao = alignment.classificacao

            stats["total"] += 1
            key = alignment.classificacao.lower().replace(" ", "_")
            if key in stats:
                stats[key] += 1

        await session.commit()
        logger.info("alignment_update_done", **stats)
        return stats

    async def get_aliados(self, session: AsyncSession, min_indice: float = 50.0) -> list[dict[str, Any]]:
        """Retorna parlamentares aliados (indice >= min_indice)."""
        stmt = (
            select(Parlamentar)
            .where(Parlamentar.indice_alinhamento >= min_indice)
            .order_by(Parlamentar.indice_alinhamento.desc())
        )
        result = await session.execute(stmt)
        parlamentares = result.scalars().all()

        return [
            {
                "id": p.id,
                "nome": p.nome_parlamentar or p.nome_civil,
                "partido": p.partido,
                "uf": p.uf,
                "indice": float(p.indice_alinhamento) if p.indice_alinhamento else 0,
                "classificacao": p.classificacao,
                "total_votos": p.total_votos_setor,
                "votos_favor": p.votos_favor_setor,
            }
            for p in parlamentares
        ]

    async def get_aliados_ids(self, session: AsyncSession) -> set[str]:
        """Retorna set de source_ids de parlamentares aliados (para scoring)."""
        stmt = (
            select(Parlamentar.source_id)
            .where(Parlamentar.classificacao.in_(["Aliado Forte", "Aliado"]))
        )
        result = await session.execute(stmt)
        return set(result.scalars().all())
