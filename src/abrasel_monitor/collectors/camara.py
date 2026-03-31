"""Coletor da Camara dos Deputados.

Fonte: API REST https://dadosabertos.camara.leg.br/api/v2
Cobertura: desde a 48a legislatura (1987)
Volume estimado: ~250.000 proposicoes

Endpoints utilizados conforme doc:
- /proposicoes
- /proposicoes/{id}/tramitacoes
- /proposicoes/{id}/votacoes
- /proposicoes/{id}/autores
- /proposicoes/{id}/temas
- /deputados
- /deputados/{id}/discursos
- /eventos
- /votacoes/{id}/votos
"""

from __future__ import annotations

from typing import Any

import structlog

from abrasel_monitor._shared.http_client import MonitorHTTPClient, create_camara_client
from abrasel_monitor.collectors.base import BaseCollector, ProposicaoRaw

logger = structlog.get_logger()

# Tipos de proposicao monitorados (conforme RF-01)
TIPOS_PROPOSICAO = ["PL", "PEC", "PLP", "PDC", "MPV", "EMC", "REQ", "IND"]


class CamaraCollector(BaseCollector):
    """Coletor para a API da Camara dos Deputados."""

    source_name = "CAMARA"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_camara_client())

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        """Coleta proposicoes da Camara por periodo e tipo."""
        ano_fim = ano_fim or ano_inicio
        tipos = tipos or TIPOS_PROPOSICAO
        all_proposicoes: list[ProposicaoRaw] = []

        for tipo in tipos:
            params: dict[str, Any] = {
                "siglaTipo": tipo,
                "ano": ano_inicio,
                "ordenarPor": "id",
                "ordem": "ASC",
            }

            try:
                raw_items = await self.client.get_paginated(
                    "proposicoes",
                    params=params,
                    page_param="pagina",
                    items_param="itens",
                    items_per_page=100,
                    data_key="dados",
                )

                for item in raw_items:
                    prop = self._parse_proposicao(item)
                    if prop:
                        all_proposicoes.append(prop)

                logger.info(
                    "camara_proposicoes_coletadas",
                    tipo=tipo,
                    ano=ano_inicio,
                    count=len(raw_items),
                )
            except Exception as e:
                logger.error("camara_proposicoes_erro", tipo=tipo, ano=ano_inicio, error=str(e))

        return all_proposicoes

    def _parse_proposicao(self, raw: dict[str, Any]) -> ProposicaoRaw | None:
        try:
            return ProposicaoRaw(
                source_id=str(raw.get("id", "")),
                source="CAMARA",
                tipo=raw.get("siglaTipo", ""),
                numero=raw.get("numero"),
                ano=raw.get("ano", 0),
                ementa=raw.get("ementa", ""),
                ementa_detalhada=raw.get("ementaDetalhada"),
                situacao_atual=raw.get("statusProposicao", {}).get("descricaoSituacao") if isinstance(raw.get("statusProposicao"), dict) else None,
                data_apresentacao=raw.get("dataApresentacao"),
                casa_origem="Camara",
                url_inteiro_teor=raw.get("urlInteiroTeor"),
                raw_data=raw,
            )
        except Exception as e:
            logger.warning("camara_parse_error", raw_id=raw.get("id"), error=str(e))
            return None

    async def collect_tramitacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta historico de tramitacao de uma proposicao."""
        try:
            data = await self.client.get(f"proposicoes/{proposicao_id}/tramitacoes")
            items = data.get("dados", []) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error("camara_tramitacoes_erro", proposicao_id=proposicao_id, error=str(e))
            return []

    async def collect_votacoes(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta votacoes de uma proposicao."""
        try:
            data = await self.client.get(f"proposicoes/{proposicao_id}/votacoes")
            items = data.get("dados", []) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error("camara_votacoes_erro", proposicao_id=proposicao_id, error=str(e))
            return []

    async def collect_votos_nominais(self, votacao_id: str) -> list[dict[str, Any]]:
        """Coleta votos individuais de uma votacao."""
        try:
            data = await self.client.get(f"votacoes/{votacao_id}/votos")
            items = data.get("dados", []) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error("camara_votos_erro", votacao_id=votacao_id, error=str(e))
            return []

    async def collect_autores(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta autores de uma proposicao."""
        try:
            data = await self.client.get(f"proposicoes/{proposicao_id}/autores")
            items = data.get("dados", []) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error("camara_autores_erro", proposicao_id=proposicao_id, error=str(e))
            return []

    async def collect_temas(self, proposicao_id: str) -> list[dict[str, Any]]:
        """Coleta temas de uma proposicao."""
        try:
            data = await self.client.get(f"proposicoes/{proposicao_id}/temas")
            items = data.get("dados", []) if isinstance(data, dict) else data
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error("camara_temas_erro", proposicao_id=proposicao_id, error=str(e))
            return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        """Coleta lista de deputados."""
        params: dict[str, Any] = {"ordem": "ASC", "ordenarPor": "nome"}
        if legislatura:
            params["idLegislatura"] = legislatura

        try:
            return await self.client.get_paginated(
                "deputados",
                params=params,
                items_per_page=100,
                data_key="dados",
            )
        except Exception as e:
            logger.error("camara_parlamentares_erro", legislatura=legislatura, error=str(e))
            return []

    async def collect_discursos(self, parlamentar_id: str, data_inicio: str | None = None) -> list[dict[str, Any]]:
        """Coleta discursos de um deputado."""
        params: dict[str, Any] = {"ordenarPor": "dataHoraInicio", "ordem": "DESC"}
        if data_inicio:
            params["dataInicio"] = data_inicio

        try:
            return await self.client.get_paginated(
                f"deputados/{parlamentar_id}/discursos",
                params=params,
                items_per_page=100,
                data_key="dados",
            )
        except Exception as e:
            logger.error("camara_discursos_erro", parlamentar_id=parlamentar_id, error=str(e))
            return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        """Coleta eventos (pauta de plenario e comissoes)."""
        params: dict[str, Any] = {
            "dataInicio": data_inicio,
            "dataFim": data_fim,
            "ordem": "ASC",
            "ordenarPor": "dataHoraInicio",
        }

        try:
            return await self.client.get_paginated(
                "eventos",
                params=params,
                items_per_page=100,
                data_key="dados",
            )
        except Exception as e:
            logger.error("camara_agenda_erro", error=str(e))
            return []

    async def collect_orgaos(self) -> list[dict[str, Any]]:
        """Coleta comissoes e orgaos da Camara."""
        try:
            return await self.client.get_paginated(
                "orgaos",
                params={"ordem": "ASC", "ordenarPor": "nome"},
                items_per_page=100,
                data_key="dados",
            )
        except Exception as e:
            logger.error("camara_orgaos_erro", error=str(e))
            return []
