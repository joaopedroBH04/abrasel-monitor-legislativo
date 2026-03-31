"""Orquestrador central do Monitor Legislativo.

Coordena os diferentes tipos de execucao conforme secao 10 do documento:
- Full Load (historico desde 1988)
- Incremental Diario (06h00)
- Varredura de Agenda (07h00)
- Varredura Express (a cada 4h em dias uteis)
- Relatorio Semanal (sexta 18h)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from abrasel_monitor.alertas.engine import AlertEngine
from abrasel_monitor.collectors.camara import CamaraCollector
from abrasel_monitor.collectors.senado import SenadoCollector
from abrasel_monitor.collectors.assembleias import ASSEMBLEIAS_COLLECTORS
from abrasel_monitor.database import async_session
from abrasel_monitor.etl.pipeline import ETLPipeline
from abrasel_monitor.parlamentares.alignment import AlignmentEngine

logger = structlog.get_logger()


class Orchestrator:
    """Orquestrador central que coordena todos os componentes."""

    def __init__(self):
        self.etl = ETLPipeline()
        self.alert_engine = AlertEngine()
        self.alignment_engine = AlignmentEngine()

    async def run_incremental_daily(self) -> dict[str, Any]:
        """Execucao incremental diaria - coleta novidades de todas as fontes.

        Agendamento: Diario as 06h00 (conforme secao 10.1).
        """
        logger.info("incremental_daily_start")
        results: dict[str, Any] = {}

        # Camara
        results["camara"] = await self._collect_and_process(CamaraCollector(), "incremental")

        # Senado
        results["senado"] = await self._collect_and_process(SenadoCollector(), "incremental")

        # Assembleias
        for name, collector_cls in ASSEMBLEIAS_COLLECTORS.items():
            try:
                results[name.lower()] = await self._collect_and_process(collector_cls(), "incremental")
            except Exception as e:
                logger.error("incremental_assembleia_erro", assembleia=name, error=str(e))
                results[name.lower()] = {"error": str(e)}

        # Atualizar alinhamento parlamentar
        async with async_session() as session:
            await self.alignment_engine.update_all_alignments(session)

        logger.info("incremental_daily_done", results=results)
        return results

    async def run_agenda_scan(self) -> dict[str, Any]:
        """Varredura de agenda - busca pauta dos proximos 3 dias.

        Agendamento: Diario as 07h00 (conforme secao 10.1).
        """
        logger.info("agenda_scan_start")
        now = datetime.now(timezone.utc)
        data_inicio = now.strftime("%Y-%m-%d")
        data_fim = (now.replace(day=now.day + 3)).strftime("%Y-%m-%d")

        results: dict[str, Any] = {}

        # Camara
        camara = CamaraCollector()
        try:
            agenda_camara = await camara.collect_agenda(data_inicio, data_fim)
            results["camara_agenda"] = len(agenda_camara)
        except Exception as e:
            logger.error("agenda_camara_erro", error=str(e))
        finally:
            await camara.client.close()

        # Senado
        senado = SenadoCollector()
        try:
            agenda_senado = await senado.collect_agenda(data_inicio, data_fim)
            results["senado_agenda"] = len(agenda_senado)
        except Exception as e:
            logger.error("agenda_senado_erro", error=str(e))
        finally:
            await senado.client.close()

        # Disparar alertas
        async with async_session() as session:
            alertas_count = await self.alert_engine.dispatch_all_pending(session)
            results["alertas_disparados"] = alertas_count

        logger.info("agenda_scan_done", results=results)
        return results

    async def run_express_scan(self) -> dict[str, Any]:
        """Varredura express - verifica votacoes em andamento.

        Agendamento: A cada 4h em dias uteis (conforme secao 10.1).
        """
        logger.info("express_scan_start")

        async with async_session() as session:
            alertas_count = await self.alert_engine.dispatch_all_pending(session)

        return {"alertas_disparados": alertas_count}

    async def run_full_load(self, ano_inicio: int = 1988) -> dict[str, Any]:
        """Carga historica completa desde 1988.

        Conforme secao 12: execucao unica antes de producao.
        """
        logger.info("full_load_start", ano_inicio=ano_inicio)
        results: dict[str, Any] = {}

        # Fase 1: Camara (3-5 dias estimados)
        results["camara"] = await self._full_load_source(CamaraCollector(), ano_inicio)

        # Fase 2: Senado (1-2 dias estimados)
        results["senado"] = await self._full_load_source(SenadoCollector(), 1991)

        # Fase 3: Assembleias
        assembleias_inicio = {
            "ALESP": 1990, "ALMG": 1988, "ALERJ": 1995,
            "ALRS": 1999, "ALEP": 2002,
        }
        for name, collector_cls in ASSEMBLEIAS_COLLECTORS.items():
            inicio = assembleias_inicio.get(name, 2000)
            try:
                results[name.lower()] = await self._full_load_source(collector_cls(), inicio)
            except Exception as e:
                logger.error("full_load_assembleia_erro", assembleia=name, error=str(e))

        logger.info("full_load_done", results=results)
        return results

    async def _collect_and_process(
        self,
        collector: Any,
        tipo_execucao: str,
    ) -> dict[str, Any]:
        """Coleta e processa dados de uma fonte."""
        try:
            proposicoes = await collector.run_incremental()

            # Coletar os raw para ETL
            current_year = datetime.now(timezone.utc).year
            raw_props = await collector.collect_proposicoes(ano_inicio=current_year)

            if raw_props:
                async with async_session() as session:
                    result = await self.etl.run_full_pipeline(
                        session, raw_props, collector.source_name, tipo_execucao
                    )
                    return result

            return proposicoes
        except Exception as e:
            logger.error("collect_process_error", source=collector.source_name, error=str(e))
            return {"error": str(e)}
        finally:
            await collector.client.close()

    async def _full_load_source(self, collector: Any, ano_inicio: int) -> dict[str, Any]:
        """Executa full load para uma fonte especifica."""
        try:
            stats = await collector.run_full_load(ano_inicio=ano_inicio)
            return stats
        except Exception as e:
            return {"error": str(e)}
        finally:
            await collector.client.close()
