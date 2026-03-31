"""CLI principal do Abrasel Monitor Legislativo.

Uso: abrasel-monitor [COMANDO] [OPCOES]

Comandos disponiveis:
- collect: Executa coleta de dados de uma fonte
- full-load: Executa carga historica completa desde 1988
- score: Reprocessa scoring de todas as proposicoes
- alignment: Recalcula indice de alinhamento parlamentar
- alerts: Verifica e dispara alertas pendentes
- report: Gera relatorio semanal/mensal
- dashboard: Inicia dashboard Streamlit
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.table import Table

from abrasel_monitor._shared.logging import setup_logging

app = typer.Typer(
    name="abrasel-monitor",
    help="Monitor Legislativo Abrasel - Robo de Monitoramento Parlamentar",
)
console = Console()


@app.command()
def collect(
    source: str = typer.Argument(help="Fonte: camara, senado, alesp, almg, alerj, alrs, alep, alal, aleam, cldf, alems"),
    mode: str = typer.Option("incremental", help="Modo: incremental ou full_load"),
    ano_inicio: int = typer.Option(2024, help="Ano inicio para coleta"),
    ano_fim: int | None = typer.Option(None, help="Ano fim (default: ano atual)"),
):
    """Executa coleta de dados de uma fonte legislativa."""
    setup_logging()
    console.print(f"[bold blue]Iniciando coleta: {source} ({mode})[/bold blue]")
    asyncio.run(_run_collect(source, mode, ano_inicio, ano_fim))


async def _run_collect(source: str, mode: str, ano_inicio: int, ano_fim: int | None) -> None:
    from abrasel_monitor.collectors.camara import CamaraCollector
    from abrasel_monitor.collectors.senado import SenadoCollector
    from abrasel_monitor.collectors.assembleias import ASSEMBLEIAS_COLLECTORS

    collectors = {
        "camara": CamaraCollector,
        "senado": SenadoCollector,
    }

    # Adicionar assembleias
    for key, cls in ASSEMBLEIAS_COLLECTORS.items():
        collectors[key.lower()] = cls

    collector_cls = collectors.get(source.lower())
    if not collector_cls:
        console.print(f"[red]Fonte desconhecida: {source}[/red]")
        console.print(f"Fontes disponiveis: {', '.join(collectors.keys())}")
        return

    collector = collector_cls()

    try:
        if mode == "full_load":
            stats = await collector.run_full_load(ano_inicio=ano_inicio)
        else:
            stats = await collector.run_incremental()

        console.print(f"[green]Coleta concluida![/green]")
        _print_stats(stats)
    except Exception as e:
        console.print(f"[red]Erro na coleta: {e}[/red]")
    finally:
        await collector.client.close()


@app.command()
def full_load(
    ano_inicio: int = typer.Option(1988, help="Ano de inicio da carga historica"),
    sources: str = typer.Option("camara,senado", help="Fontes separadas por virgula"),
):
    """Executa carga historica completa desde 1988."""
    setup_logging()
    console.print(f"[bold yellow]CARGA HISTORICA desde {ano_inicio}[/bold yellow]")
    console.print(f"Fontes: {sources}")

    source_list = [s.strip() for s in sources.split(",")]
    for source in source_list:
        console.print(f"\n[blue]Processando: {source}...[/blue]")
        asyncio.run(_run_collect(source, "full_load", ano_inicio, None))


@app.command()
def pipeline(
    source: str = typer.Argument(help="Fonte para executar pipeline completo"),
    ano: int = typer.Option(2024, help="Ano para processar"),
):
    """Executa pipeline completo: Coleta -> Silver -> Gold (com scoring)."""
    setup_logging()
    console.print(f"[bold blue]Pipeline completo: {source} (ano={ano})[/bold blue]")
    asyncio.run(_run_pipeline(source, ano))


async def _run_pipeline(source: str, ano: int) -> None:
    from abrasel_monitor.collectors.camara import CamaraCollector
    from abrasel_monitor.collectors.senado import SenadoCollector
    from abrasel_monitor.database import async_session
    from abrasel_monitor.etl.pipeline import ETLPipeline

    collectors = {"camara": CamaraCollector, "senado": SenadoCollector}
    collector_cls = collectors.get(source.lower())
    if not collector_cls:
        console.print(f"[red]Fonte desconhecida: {source}[/red]")
        return

    collector = collector_cls()
    etl = ETLPipeline()

    try:
        proposicoes = await collector.collect_proposicoes(ano_inicio=ano)
        console.print(f"[green]Coletadas {len(proposicoes)} proposicoes[/green]")

        async with async_session() as session:
            result = await etl.run_full_pipeline(session, proposicoes, source)
            console.print(f"[green]Pipeline concluido![/green]")
            console.print(f"Silver: {result['silver']['total']} | Gold: {result['gold']}")
    finally:
        await collector.client.close()


@app.command()
def score(
    recalculate: bool = typer.Option(True, help="Recalcular todos os scores"),
):
    """Reprocessa scoring de todas as proposicoes."""
    setup_logging()
    console.print("[bold blue]Reprocessando scoring...[/bold blue]")
    asyncio.run(_run_score())


async def _run_score() -> None:
    from abrasel_monitor.database import async_session
    from abrasel_monitor.scoring.engine import ScoringEngine
    from abrasel_monitor.models import Proposicao
    from sqlalchemy import select

    engine = ScoringEngine()
    async with async_session() as session:
        result = await session.execute(select(Proposicao))
        proposicoes = result.scalars().all()

        updated = 0
        for prop in proposicoes:
            scoring = engine.score_proposicao(
                ementa=prop.ementa,
                ementa_detalhada=prop.ementa_detalhada,
            )
            prop.relevancia_score = scoring.score
            prop.relevancia_nivel = scoring.nivel
            prop.keywords_matched = scoring.keywords_matched or None
            updated += 1

        await session.commit()
        console.print(f"[green]{updated} proposicoes rescored[/green]")


@app.command()
def alignment():
    """Recalcula indice de alinhamento de todos os parlamentares."""
    setup_logging()
    console.print("[bold blue]Recalculando alinhamento parlamentar...[/bold blue]")
    asyncio.run(_run_alignment())


async def _run_alignment() -> None:
    from abrasel_monitor.database import async_session
    from abrasel_monitor.parlamentares.alignment import AlignmentEngine

    engine = AlignmentEngine()
    async with async_session() as session:
        stats = await engine.update_all_alignments(session)
        _print_stats(stats)


@app.command()
def alerts():
    """Verifica e dispara alertas pendentes."""
    setup_logging()
    console.print("[bold blue]Verificando alertas...[/bold blue]")
    asyncio.run(_run_alerts())


async def _run_alerts() -> None:
    from abrasel_monitor.database import async_session
    from abrasel_monitor.alertas.engine import AlertEngine

    engine = AlertEngine()
    async with async_session() as session:
        count = await engine.dispatch_all_pending(session)
        console.print(f"[green]{count} alertas disparados[/green]")


@app.command()
def dashboard():
    """Inicia o dashboard Streamlit."""
    import subprocess
    console.print("[bold blue]Iniciando dashboard Streamlit...[/bold blue]")
    subprocess.run(["streamlit", "run", "src/abrasel_monitor/dashboard/app.py"])


@app.command()
def status():
    """Mostra status geral do sistema."""
    setup_logging()
    console.print("[bold blue]Status do Monitor Legislativo Abrasel[/bold blue]")
    asyncio.run(_show_status())


async def _show_status() -> None:
    from abrasel_monitor.database import async_session
    from abrasel_monitor.models import Proposicao, Parlamentar, ExecucaoRobo
    from sqlalchemy import select, func

    try:
        async with async_session() as session:
            # Contagens
            total_prop = await session.scalar(select(func.count(Proposicao.id)))
            total_parl = await session.scalar(select(func.count(Parlamentar.id)))

            # Por relevancia
            for nivel in ["Alta", "Media", "Baixa", "Irrelevante"]:
                count = await session.scalar(
                    select(func.count(Proposicao.id)).where(Proposicao.relevancia_nivel == nivel)
                )
                console.print(f"  {nivel}: {count}")

            # Ultima execucao
            stmt = select(ExecucaoRobo).order_by(ExecucaoRobo.inicio.desc()).limit(5)
            result = await session.execute(stmt)
            execucoes = result.scalars().all()

            table = Table(title="Ultimas Execucoes")
            table.add_column("Fonte")
            table.add_column("Tipo")
            table.add_column("Status")
            table.add_column("Coletados")
            table.add_column("Inicio")

            for ex in execucoes:
                table.add_row(ex.fonte, ex.tipo_execucao, ex.status, str(ex.total_coletado), str(ex.inicio))

            console.print(f"\nTotal proposicoes: {total_prop}")
            console.print(f"Total parlamentares: {total_parl}")
            console.print(table)
    except Exception as e:
        console.print(f"[yellow]Banco nao disponivel: {e}[/yellow]")
        console.print("Execute as migrations primeiro: alembic upgrade head")


def _print_stats(stats: dict) -> None:
    table = Table(title="Estatisticas")
    table.add_column("Metrica")
    table.add_column("Valor")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)


if __name__ == "__main__":
    app()
