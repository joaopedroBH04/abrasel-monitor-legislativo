"""Coletor do Senado Federal.

Fonte: API OpenData https://legis.senado.leg.br/dadosabertos
Cobertura: desde a 49a legislatura (1991)
Volume estimado: ~80.000 materias

A API do Senado retorna XML por padrao, mas aceita JSON via header Accept.
"""

from __future__ import annotations

from typing import Any

import structlog

from abrasel_monitor._shared.http_client import MonitorHTTPClient, create_senado_client
from abrasel_monitor.collectors.base import BaseCollector, ProposicaoRaw

logger = structlog.get_logger()


class SenadoCollector(BaseCollector):
    """Coletor para a API do Senado Federal."""

    source_name = "SENADO"

    def __init__(self, client: MonitorHTTPClient | None = None):
        super().__init__(client or create_senado_client())

    async def collect_proposicoes(
        self,
        ano_inicio: int,
        ano_fim: int | None = None,
        tipos: list[str] | None = None,
    ) -> list[ProposicaoRaw]:
        """Coleta materias legislativas do Senado por periodo."""
        ano_fim = ano_fim or ano_inicio
        all_proposicoes: list[ProposicaoRaw] = []

        for ano in range(ano_inicio, ano_fim + 1):
            params: dict[str, Any] = {
                "ano": ano,
                "v": 7,
            }

            try:
                data = await self.client.get("materia/pesquisa/lista", params=params)
                materias = self._extract_materias(data)

                for materia in materias:
                    prop = self._parse_materia(materia)
                    if prop:
                        all_proposicoes.append(prop)

                logger.info("senado_proposicoes_coletadas", ano=ano, count=len(materias))
            except Exception as e:
                logger.error("senado_proposicoes_erro", ano=ano, error=str(e))

        return all_proposicoes

    def _extract_materias(self, data: Any) -> list[dict[str, Any]]:
        """Extrai lista de materias da resposta do Senado (estrutura aninhada)."""
        if isinstance(data, dict):
            pesquisa = data.get("PesquisaBasicaMateria", {})
            materias = pesquisa.get("Materias", {})
            materia_list = materias.get("Materia", [])
            if isinstance(materia_list, dict):
                return [materia_list]
            return materia_list if isinstance(materia_list, list) else []
        return []

    def _parse_materia(self, raw: dict[str, Any]) -> ProposicaoRaw | None:
        try:
            codigo = raw.get("CodigoMateria", raw.get("IdentificacaoMateria", {}).get("CodigoMateria", ""))
            ident = raw.get("IdentificacaoMateria", raw)

            return ProposicaoRaw(
                source_id=str(codigo),
                source="SENADO",
                tipo=ident.get("SiglaSubtipoMateria", ident.get("SiglaTipoMateria", "")),
                numero=self._safe_int(ident.get("NumeroMateria")),
                ano=self._safe_int(ident.get("AnoMateria", 0)),
                ementa=raw.get("EmentaMateria", raw.get("Ementa", "")),
                ementa_detalhada=raw.get("ExplicacaoEmentaMateria"),
                situacao_atual=raw.get("SituacaoAtual", {}).get("Autuacoes", {}).get("Autuacao", {}).get("Situacao", {}).get("DescricaoSituacao") if isinstance(raw.get("SituacaoAtual"), dict) else None,
                data_apresentacao=raw.get("DataApresentacao", ident.get("DataApresentacao")),
                casa_origem="Senado",
                url_inteiro_teor=raw.get("UrlTextoAssociado"),
                raw_data=raw,
            )
        except Exception as e:
            logger.warning("senado_parse_error", error=str(e))
            return None

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0

    async def collect_tramitacoes(self, materia_codigo: str) -> list[dict[str, Any]]:
        """Coleta tramitacao de uma materia."""
        try:
            data = await self.client.get(f"materia/{materia_codigo}/tramitando")
            if isinstance(data, dict):
                tramitacoes = data.get("MovimentacaoMateria", {}).get("Materia", {}).get("Tramitacoes", {}).get("Tramitacao", [])
                if isinstance(tramitacoes, dict):
                    return [tramitacoes]
                return tramitacoes if isinstance(tramitacoes, list) else []
            return []
        except Exception as e:
            logger.error("senado_tramitacoes_erro", materia=materia_codigo, error=str(e))
            return []

    async def collect_votacoes(self, materia_codigo: str) -> list[dict[str, Any]]:
        """Coleta votacoes de uma materia."""
        try:
            data = await self.client.get(f"materia/{materia_codigo}/votacoes")
            if isinstance(data, dict):
                votacoes = data.get("VotacaoMateria", {}).get("Materia", {}).get("Votacoes", {}).get("Votacao", [])
                if isinstance(votacoes, dict):
                    return [votacoes]
                return votacoes if isinstance(votacoes, list) else []
            return []
        except Exception as e:
            logger.error("senado_votacoes_erro", materia=materia_codigo, error=str(e))
            return []

    async def collect_parlamentares(self, legislatura: int | None = None) -> list[dict[str, Any]]:
        """Coleta lista de senadores."""
        try:
            endpoint = "senador/lista/atual" if not legislatura else f"senador/lista/legislatura/{legislatura}"
            data = await self.client.get(endpoint)

            if isinstance(data, dict):
                parlamentares = data.get("ListaParlamentarEmExercicio", data.get("ListaParlamentarLegislatura", {}))
                senadores = parlamentares.get("Parlamentares", {}).get("Parlamentar", [])
                if isinstance(senadores, dict):
                    return [senadores]
                return senadores if isinstance(senadores, list) else []
            return []
        except Exception as e:
            logger.error("senado_parlamentares_erro", legislatura=legislatura, error=str(e))
            return []

    async def collect_discursos(self, senador_codigo: str, data_inicio: str | None = None) -> list[dict[str, Any]]:
        """Coleta pronunciamentos de um senador."""
        try:
            params: dict[str, Any] = {}
            if data_inicio:
                params["dataInicio"] = data_inicio

            data = await self.client.get(f"senador/{senador_codigo}/discursos", params=params)
            if isinstance(data, dict):
                discursos = data.get("DiscursosParlamentar", {}).get("Parlamentar", {}).get("Pronunciamentos", {}).get("Pronunciamento", [])
                if isinstance(discursos, dict):
                    return [discursos]
                return discursos if isinstance(discursos, list) else []
            return []
        except Exception as e:
            logger.error("senado_discursos_erro", senador=senador_codigo, error=str(e))
            return []

    async def collect_agenda(self, data_inicio: str, data_fim: str) -> list[dict[str, Any]]:
        """Coleta pauta do plenario do Senado."""
        try:
            params = {"dataInicio": data_inicio, "dataFim": data_fim}
            data = await self.client.get("plenario/agenda/mes", params=params)

            if isinstance(data, dict):
                sessoes = data.get("AgendaPlenario", {}).get("Sessoes", {}).get("Sessao", [])
                if isinstance(sessoes, dict):
                    return [sessoes]
                return sessoes if isinstance(sessoes, list) else []
            return []
        except Exception as e:
            logger.error("senado_agenda_erro", error=str(e))
            return []

    async def collect_comissoes(self) -> list[dict[str, Any]]:
        """Coleta comissoes do Senado."""
        try:
            data = await self.client.get("comissao/lista")
            if isinstance(data, dict):
                comissoes = data.get("ListaComissoes", {}).get("Comissoes", {}).get("Comissao", [])
                if isinstance(comissoes, dict):
                    return [comissoes]
                return comissoes if isinstance(comissoes, list) else []
            return []
        except Exception as e:
            logger.error("senado_comissoes_erro", error=str(e))
            return []
