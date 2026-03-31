# Abrasel Monitor Legislativo

## Visao Geral
Robo de monitoramento parlamentar para a Abrasel (Associacao Brasileira de Bares e Restaurantes).
Automatiza vigilancia, coleta e classificacao de proposicoes legislativas relevantes para o setor de alimentacao fora do lar.

## Arquitetura
- **Python 3.12+** com async/await (httpx)
- **Arquitetura Medallion**: Bronze (S3 raw) -> Silver (S3 normalizado) -> Gold (PostgreSQL enriquecido)
- **Padrao de Adaptadores**: cada fonte de dados e um coletor independente que entrega o mesmo schema
- **Scoring Engine**: classificacao automatica por keywords + temas + autores aliados
- **Infraestrutura AWS**: ECS Fargate + RDS + S3 + EventBridge + SES

## Comandos
```bash
# Desenvolvimento local
docker-compose up -d postgres redis localstack
pip install -e ".[dev]"

# CLI
abrasel-monitor collect camara --mode incremental
abrasel-monitor full-load --ano-inicio 1988 --sources camara,senado
abrasel-monitor pipeline camara --ano 2024
abrasel-monitor score
abrasel-monitor alignment
abrasel-monitor alerts
abrasel-monitor dashboard
abrasel-monitor status

# Testes
pytest tests/ -v
ruff check src/
mypy src/abrasel_monitor/

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "descricao"

# Docker
docker-compose up --build
```

## Estrutura de Diretorios
```
src/abrasel_monitor/
  _shared/          # HTTP client, rate limiter, checkpoint, S3
  collectors/       # Coletores: Camara, Senado, 9 Assembleias
  etl/              # Pipeline Bronze->Silver->Gold
  scoring/          # Motor de relevancia (keywords + temas)
  parlamentares/    # Indice de alinhamento
  alertas/          # Email (SES) + Slack
  dashboard/        # Streamlit (prototipo)
  cli.py            # CLI principal (Typer)
  orchestrator.py   # Orquestrador central
  models.py         # SQLAlchemy models
  settings.py       # Configuracao (Pydantic Settings)
config/
  keywords.yaml     # Taxonomia de palavras-chave (gerenciavel sem deploy)
terraform/          # IaC AWS
```

## Fontes de Dados
- Camara dos Deputados: API REST (dados.camara.leg.br)
- Senado Federal: API OpenData (legis.senado.leg.br)
- Assembleias: ALESP, ALMG, ALERJ, ALRS, ALEP, ALAL, ALEAM, CLDF, ALEMS

## Integracao com mcp-brasil
O projeto usa `mcp-brasil` como dependencia para acesso via MCP tools as APIs brasileiras.
Os coletores proprios sao usados para controle fino de rate limiting e persistencia.
