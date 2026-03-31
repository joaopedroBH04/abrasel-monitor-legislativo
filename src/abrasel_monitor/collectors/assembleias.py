"""Coletores para Assembleias Legislativas Estaduais.

Estados prioritarios (7 pilotos conforme obs. do documento):
AL, AM, DF, MS, PR, RJ, RS

Estados originais do documento: SP, RJ, MG, RS, PR

Estrategia: adaptadores padronizados por estado que entregam o mesmo
schema interno (ProposicaoRaw), independente da fonte (API ou scraping).
"""

from __future__ import annotations

from typing import Any

import structlog

from abrasel_monitor._shared.http_client import MonitorHTTPClient, create_assembleia_client
from abrasel_monitor.collectors.base import BaseCollector, ProposicaoRaw

logger = structlog.get_logger()


# ============================================================================
# ALESP - Assembleia Legislativa de Sao Paulo
# API REST: www.al.sp.gov.br
# ============================================================================
class ALESPCollector(BaseCollector):
    """Coletor para ALESP - Sao Paulo. API REST + scraping complementar."""

    source_name = "ALESP"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://www.al.sp.gov.br/alesp/dados-abertos"))

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        ano_fim = ano_fim or ano_inicio
        all_proposicoes: list[ProposicaoRaw] = []

        for ano in range(ano_inicio, ano_fim + 1):
            try:
                data = await self.client.get("proposituras", params={"ano": ano})
                items = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
                for item in items:
                    prop = ProposicaoRaw(
                        source_id=str(item.get("id", item.get("IdDocumento", ""))),
                        source="ALESP",
                        tipo=item.get("tipo", item.get("SiglaTipoDocumento", "")),
                        numero=item.get("numero", item.get("NroDocumento")),
                        ano=ano,
                        ementa=item.get("ementa", item.get("Ementa", "")),
                        data_apresentacao=item.get("dataApresentacao", item.get("DtEntrada")),
                        casa_origem="Assembleia",
                        raw_data=item,
                    )
                    all_proposicoes.append(prop)
                logger.info("alesp_proposicoes_coletadas", ano=ano, count=len(items))
            except Exception as e:
                logger.error("alesp_proposicoes_erro", ano=ano, error=str(e))

        return all_proposicoes

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        try:
            data = await self.client.get(f"proposituras/{proposicao_id}/tramitacoes")
            return data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("alesp_tramitacoes_erro", error=str(e))
            return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        try:
            data = await self.client.get(f"proposituras/{proposicao_id}/votacoes")
            return data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("alesp_votacoes_erro", error=str(e))
            return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        try:
            data = await self.client.get("deputados")
            return data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("alesp_parlamentares_erro", error=str(e))
            return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        try:
            data = await self.client.get("sessoes", params={"dataInicio": data_inicio, "dataFim": data_fim})
            return data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("alesp_agenda_erro", error=str(e))
            return []


# ============================================================================
# ALMG - Assembleia Legislativa de Minas Gerais
# API REST bem documentada: www.almg.gov.br
# ============================================================================
class ALMGCollector(BaseCollector):
    """Coletor para ALMG - Minas Gerais. API REST documentada."""

    source_name = "ALMG"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://dadosabertos.almg.gov.br/ws"))

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        ano_fim = ano_fim or ano_inicio
        all_proposicoes: list[ProposicaoRaw] = []

        for ano in range(ano_inicio, ano_fim + 1):
            try:
                data = await self.client.get(
                    f"proposicoes/pesquisa/direcionada",
                    params={"ano": ano, "tp": "PL,PLC,PEC"},
                )
                items = data.get("lista", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                for item in items:
                    prop = ProposicaoRaw(
                        source_id=str(item.get("id", "")),
                        source="ALMG",
                        tipo=item.get("siglaTipo", ""),
                        numero=item.get("numero"),
                        ano=ano,
                        ementa=item.get("ementa", ""),
                        data_apresentacao=item.get("dataApresentacao"),
                        casa_origem="Assembleia",
                        raw_data=item,
                    )
                    all_proposicoes.append(prop)
                logger.info("almg_proposicoes_coletadas", ano=ano, count=len(items))
            except Exception as e:
                logger.error("almg_proposicoes_erro", ano=ano, error=str(e))

        return all_proposicoes

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        try:
            data = await self.client.get(f"proposicoes/{proposicao_id}/tramitacoes")
            return data.get("lista", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("almg_tramitacoes_erro", error=str(e))
            return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []  # ALMG nao expoe votacoes nominais via API

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        try:
            data = await self.client.get("deputados/em_exercicio")
            return data.get("lista", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        except Exception as e:
            logger.error("almg_parlamentares_erro", error=str(e))
            return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        try:
            data = await self.client.get("reunioes/plenario", params={"dataInicio": data_inicio, "dataFim": data_fim})
            return data.get("lista", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error("almg_agenda_erro", error=str(e))
            return []


# ============================================================================
# ALERJ - Assembleia Legislativa do Rio de Janeiro
# Scraping estruturado (API parcial)
# ============================================================================
class ALERJCollector(BaseCollector):
    """Coletor para ALERJ - Rio de Janeiro. Scraping estruturado."""

    source_name = "ALERJ"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("http://alfresco.alerj.rj.gov.br/alfresco/s"))

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        ano_fim = ano_fim or ano_inicio
        all_proposicoes: list[ProposicaoRaw] = []

        for ano in range(ano_inicio, ano_fim + 1):
            try:
                data = await self.client.get(
                    "api/projetos",
                    params={"ano": ano},
                )
                items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
                for item in items:
                    prop = ProposicaoRaw(
                        source_id=str(item.get("id", "")),
                        source="ALERJ",
                        tipo=item.get("tipo", ""),
                        numero=item.get("numero"),
                        ano=ano,
                        ementa=item.get("ementa", ""),
                        data_apresentacao=item.get("dataApresentacao"),
                        casa_origem="Assembleia",
                        raw_data=item,
                    )
                    all_proposicoes.append(prop)
                logger.info("alerj_proposicoes_coletadas", ano=ano, count=len(items))
            except Exception as e:
                logger.error("alerj_proposicoes_erro", ano=ano, error=str(e))

        return all_proposicoes

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


# ============================================================================
# ALRS - Assembleia Legislativa do Rio Grande do Sul
# Scraping + RSS
# ============================================================================
class ALRSCollector(BaseCollector):
    """Coletor para ALRS - Rio Grande do Sul. RSS + scraping."""

    source_name = "ALRS"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("http://www.al.rs.gov.br"))

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        # RS usa scraping - implementacao completa com Playwright em producao
        logger.info("alrs_collect_placeholder", ano_inicio=ano_inicio)
        return []

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


# ============================================================================
# ALEP - Assembleia Legislativa do Parana
# Scraping estruturado
# ============================================================================
class ALEPCollector(BaseCollector):
    """Coletor para ALEP - Parana. Scraping estruturado."""

    source_name = "ALEP"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://www.assembleia.pr.leg.br"))

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        logger.info("alep_collect_placeholder", ano_inicio=ano_inicio)
        return []

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


# ============================================================================
# Estados pilotos adicionais (conforme obs. do documento)
# AL, AM, DF, MS
# ============================================================================
class ALALCollector(BaseCollector):
    """Coletor para ALAL - Alagoas."""
    source_name = "ALAL"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://sapl.al.al.leg.br/api"))

    async def collect_proposicoes(self, ano_inicio: int, ano_fim: int | None = None, tipos: list[str] | None = None) -> list[ProposicaoRaw]:
        """Usa SAPL (Sistema de Apoio ao Processo Legislativo) - padrao em varias ALs."""
        ano_fim = ano_fim or ano_inicio
        all_proposicoes: list[ProposicaoRaw] = []
        for ano in range(ano_inicio, ano_fim + 1):
            try:
                data = await self.client.get("materia/pesquisar", params={"ano": ano})
                items = data.get("results", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                for item in items:
                    prop = ProposicaoRaw(
                        source_id=str(item.get("id", "")), source="ALAL", tipo=item.get("tipo_str", ""),
                        numero=item.get("numero"), ano=ano, ementa=item.get("ementa", ""),
                        casa_origem="Assembleia", raw_data=item,
                    )
                    all_proposicoes.append(prop)
            except Exception as e:
                logger.error("alal_proposicoes_erro", ano=ano, error=str(e))
        return all_proposicoes

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []
    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


class ALEAMCollector(BaseCollector):
    """Coletor para ALEAM - Amazonas."""
    source_name = "ALEAM"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://sapl.aleam.gov.br/api"))

    async def collect_proposicoes(self, ano_inicio: int, ano_fim: int | None = None, tipos: list[str] | None = None) -> list[ProposicaoRaw]:
        logger.info("aleam_collect_placeholder", ano_inicio=ano_inicio)
        return []
    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []
    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


class CLDFCollector(BaseCollector):
    """Coletor para CLDF - Distrito Federal."""
    source_name = "CLDF"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://legislacao.cl.df.gov.br/api"))

    async def collect_proposicoes(self, ano_inicio: int, ano_fim: int | None = None, tipos: list[str] | None = None) -> list[ProposicaoRaw]:
        logger.info("cldf_collect_placeholder", ano_inicio=ano_inicio)
        return []
    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []
    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


class ALEMSCollector(BaseCollector):
    """Coletor para ALEMS - Mato Grosso do Sul."""
    source_name = "ALEMS"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_assembleia_client("https://www.al.ms.gov.br"))

    async def collect_proposicoes(self, ano_inicio: int, ano_fim: int | None = None, tipos: list[str] | None = None) -> list[ProposicaoRaw]:
        logger.info("alems_collect_placeholder", ano_inicio=ano_inicio)
        return []
    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        return []
    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        return []
    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        return []


# Registry de todos os coletores de assembleias
ASSEMBLEIAS_COLLECTORS: dict[str, type[BaseCollector]] = {
    "ALESP": ALESPCollector,
    "ALMG": ALMGCollector,
    "ALERJ": ALERJCollector,
    "ALRS": ALRSCollector,
    "ALEP": ALEPCollector,
    "ALAL": ALALCollector,
    "ALEAM": ALEAMCollector,
    "CLDF": CLDFCollector,
    "ALEMS": ALEMSCollector,
}
