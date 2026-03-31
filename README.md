# Monitor Legislativo Abrasel

> Robô de monitoramento parlamentar para a **Abrasel** (Associação Brasileira de Bares e Restaurantes) — vigilância automatizada de proposições legislativas que impactam o setor de **alimentação fora do lar** em todo o Brasil.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Fontes de Dados](#fontes-de-dados)
- [Fluxo de Dados (Medallion)](#fluxo-de-dados-medallion)
- [Motor de Relevância (Scoring)](#motor-de-relevância-scoring)
- [Índice de Alinhamento Parlamentar](#índice-de-alinhamento-parlamentar)
- [Sistema de Alertas](#sistema-de-alertas)
- [Estrutura de Diretórios](#estrutura-de-diretórios)
- [Instalação e Configuração](#instalação-e-configuração)
- [Uso (CLI)](#uso-cli)
- [Dashboard](#dashboard)
- [Infraestrutura AWS](#infraestrutura-aws)
- [Testes](#testes)
- [Roadmap](#roadmap)

---

## Visão Geral

O **Monitor Legislativo Abrasel** automatiza a vigilância de proposições em tramitação na **Câmara dos Deputados**, no **Senado Federal** e em **9 Assembleias Legislativas estaduais**. O sistema classifica automaticamente cada proposição por relevância ao setor de alimentação fora do lar, rastreia o comportamento de parlamentares e dispara alertas para a equipe de Relações Institucionais antes de votações críticas.

### Problema que Resolve

Hoje a Abrasel faz esse monitoramento de forma manual e fragmentada, com risco real de perder janelas de atuação política. Com mais de **250.000 proposições** na Câmara desde 1987 e dezenas de novas proposições por dia, o processo manual não escala.

### Solução

| Antes | Depois |
|-------|--------|
| Planilhas manuais atualizadas semanalmente | Coleta automática diária de todas as fontes |
| Busca manual por palavras-chave | Scoring automático com pesos configuráveis |
| Alertas por WhatsApp pessoal | Alertas via Slack + Email 72h antes da votação |
| Cobertura: Câmara + Senado | Cobertura: 11 casas legislativas |
| Análise subjetiva de posição parlamentar | Índice de alinhamento calculado por histórico de votos |

---

## Arquitetura

```
                          ┌─────────────────────────────────────────┐
                          │          FONTES DE DADOS                │
                          │  Câmara  │  Senado  │  9 Assembleias    │
                          └──────────┬──────────┬────────────────────┘
                                     │          │
                          ┌──────────▼──────────▼──────────┐
                          │       COLETORES (Adapters)      │
                          │   Rate Limiter + Retry + Checkpoint │
                          └──────────────┬──────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │            BRONZE LAYER (S3)             │
                    │     Dados brutos, imutáveis, particionados │
                    │     s3://abrasel-bronze/camara/PL/2024/  │
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │            SILVER LAYER (S3)             │
                    │   Normalizado, deduplicado, schema único  │
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │      GOLD LAYER (PostgreSQL / RDS)        │
                    │  Scoring + Alinhamento + Enriquecimento   │
                    └──────┬──────────────────────────┬────────┘
                           │                          │
              ┌────────────▼──────────┐  ┌────────────▼──────────┐
              │   SISTEMA DE ALERTAS   │  │      DASHBOARD         │
              │  Slack + Email (SES)   │  │  Streamlit / Metabase  │
              └────────────────────────┘  └────────────────────────┘
```

### Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Linguagem | Python 3.12+ |
| HTTP Client | `httpx` (async, HTTP/2) |
| Validação | `pydantic` v2 |
| ORM | `SQLAlchemy` 2.0 (async) |
| Banco de Dados | PostgreSQL 16 (AWS RDS) |
| Object Storage | AWS S3 (Bronze + Silver) |
| Checkpoints | AWS DynamoDB |
| Agendamento | AWS EventBridge Scheduler |
| Contêineres | AWS ECS Fargate |
| Alertas | AWS SES + Slack Webhooks |
| Dashboard (protótipo) | Streamlit + Plotly |
| Dashboard (produção) | Metabase (self-hosted ECS) |
| IaC | Terraform |
| CI/CD | GitHub Actions |

---

## Fontes de Dados

| Casa Legislativa | Cobertura | Método | Volume Estimado |
|-----------------|-----------|--------|-----------------|
| **Câmara dos Deputados** | desde 1987 (48ª leg.) | API REST | ~250.000 proposições |
| **Senado Federal** | desde 1991 (49ª leg.) | API OpenData | ~80.000 matérias |
| **ALESP** (São Paulo) | desde 1990 | API REST | ~120.000 |
| **ALMG** (Minas Gerais) | desde 1988 | API REST | ~90.000 |
| **ALERJ** (Rio de Janeiro) | desde 1995 | Scraping | ~70.000 |
| **ALRS** (Rio Grande do Sul) | desde 1999 | RSS + Scraping | ~60.000 |
| **ALEP** (Paraná) | desde 2002 | Scraping | ~45.000 |
| **ALAL** (Alagoas) | desde 2000 | SAPL API | ~30.000 |
| **ALEAM** (Amazonas) | desde 2000 | SAPL API | ~25.000 |
| **CLDF** (Distrito Federal) | desde 2000 | API | ~20.000 |
| **ALEMS** (Mato Grosso do Sul) | desde 2000 | Scraping | ~18.000 |

---

## Fluxo de Dados (Medallion)

### Bronze Layer — Dados Brutos
- JSON bruto de cada API, **imutável**
- Particionado por `fonte/tipo/ano/mes/dia/timestamp.json`
- Retenção: 90 dias em S3 Standard, depois S3 Intelligent-Tiering

### Silver Layer — Normalizado
- Schema único `ProposicaoRaw` para todas as 11 fontes
- Deduplicação por `(source, source_id)`
- Limpeza de HTML, normalização de datas e caracteres

### Gold Layer — Enriquecido (PostgreSQL)
- Scoring de relevância calculado
- Índice de alinhamento parlamentar atualizado
- Upsert idempotente via `ON CONFLICT DO UPDATE`

---

## Motor de Relevância (Scoring)

Cada proposição recebe uma pontuação baseada em 4 critérios, conforme regras de negócio definidas com a equipe de RI da Abrasel:

```
Score = (keywords_primárias × 3) + (keywords_secundárias × 1) + (temas × 2) + (autor_aliado × 2)
```

| Critério | Peso | Exemplos |
|----------|------|---------|
| **Keyword Primária** | +3 pts cada | restaurante, bar, lanchonete, food truck, alimentação fora do lar |
| **Keyword Secundária** | +1 pt cada | SIMPLES Nacional, vigilância sanitária, delivery, jornada de trabalho |
| **Tema da Câmara** | +2 pts | Comércio/Serviços (40), Trabalho (46), Tributação (47) |
| **Autor Aliado** | +2 pts | Parlamentar com índice de alinhamento ≥ 50% |

### Classificação Final

| Score | Nível | Ação |
|-------|-------|------|
| ≥ 5 | **Alta** | Alerta imediato + acompanhamento diário |
| 3 – 4 | **Média** | Relatório semanal + monitoramento |
| 1 – 2 | **Baixa** | Arquivo + revisão mensal |
| 0 | **Irrelevante** | Descartado |

### Taxonomia de Keywords

Gerenciada via `config/keywords.yaml` — **sem necessidade de deploy** para atualizar. A equipe de RI pode editar diretamente:

```yaml
primarias:
  estabelecimentos:
    - restaurante
    - bar
    - lanchonete
    - food truck
    - dark kitchen

secundarias:
  tributacao_geral:
    - SIMPLES Nacional
    - Reforma Tributária
    - IVA / CBS / IBS

exclusao:  # Reduz falsos positivos
  - alimentação escolar
  - merenda
  - banco de alimentos
```

---

## Índice de Alinhamento Parlamentar

O sistema calcula automaticamente o índice de alinhamento de cada parlamentar com base em seu histórico de votos em proposições relevantes ao setor:

```
Índice = (Votos Favoráveis ao Setor / Total de Votações de Interesse) × 100
```

> Apenas proposições com **score ≥ 3** entram no cálculo.

| Classificação | Índice | Cor |
|--------------|--------|-----|
| **Aliado Forte** | ≥ 70% | Verde escuro |
| **Aliado** | 50% – 69% | Verde |
| **Neutro** | 30% – 49% | Amarelo |
| **Opositor** | < 30% | Vermelho |

O índice é atualizado automaticamente após cada nova coleta de votos nominais. O histórico de votos é **imutável** — cada voto é registrado com o partido do parlamentar na data da votação.

---

## Sistema de Alertas

Alertas são disparados automaticamente via **Slack** e **Email (AWS SES)**:

| Tipo de Alerta | Gatilho | Canal |
|---------------|---------|-------|
| Votação iminente | Proposição Alta relevância entra em pauta nas próximas 72h | Slack + Email |
| Nova proposição relevante | Score Alta detectado na coleta diária | Slack |
| Mudança de relatoria | Qualquer mudança de relator em proposição monitorada | Email |
| Discurso relevante | Parlamentar menciona temas do setor | Slack |
| Mudança de partido | Parlamentar aliado muda de legenda | Email |

---

## Estrutura de Diretórios

```
abrasel-monitor-legislativo/
│
├── src/abrasel_monitor/
│   ├── _shared/                  # Utilitários compartilhados
│   │   ├── http_client.py        # Cliente HTTP async (rate limit + retry)
│   │   ├── checkpoint.py         # Controle de progresso (DynamoDB/local)
│   │   ├── s3.py                 # Persistência Bronze/Silver
│   │   └── logging.py            # Logging estruturado (structlog)
│   │
│   ├── collectors/               # Coletores por fonte (Padrão Adapter)
│   │   ├── base.py               # Interface BaseCollector
│   │   ├── camara.py             # Câmara dos Deputados (API REST)
│   │   ├── senado.py             # Senado Federal (API OpenData)
│   │   └── assembleias.py        # 9 Assembleias (API + Scraping)
│   │
│   ├── etl/
│   │   └── pipeline.py           # Bronze → Silver → Gold
│   │
│   ├── scoring/
│   │   └── engine.py             # Motor de Relevância
│   │
│   ├── parlamentares/
│   │   └── alignment.py          # Índice de Alinhamento
│   │
│   ├── alertas/
│   │   └── engine.py             # Slack + SES
│   │
│   ├── dashboard/
│   │   └── app.py                # Streamlit (protótipo)
│   │
│   ├── cli.py                    # CLI (abrasel-monitor)
│   ├── orchestrator.py           # Orquestrador central
│   ├── models.py                 # SQLAlchemy models (10 tabelas)
│   ├── settings.py               # Configuração (Pydantic Settings)
│   └── database.py               # Conexão async PostgreSQL
│
├── config/
│   └── keywords.yaml             # Taxonomia de palavras-chave
│
├── migrations/                   # Alembic migrations
├── tests/                        # Pytest (unit + integration)
├── terraform/                    # IaC AWS
├── .github/workflows/ci.yml      # CI/CD (GitHub Actions)
├── docker-compose.yml            # Dev local (PG + Redis + LocalStack)
├── Dockerfile
└── pyproject.toml
```

---

## Instalação e Configuração

### Pré-requisitos

- Python 3.12+
- Docker e Docker Compose
- AWS CLI configurado (para produção)
- `gh` CLI (para deploy)

### Setup Local

```bash
# 1. Clone o repositório
git clone https://github.com/joaopedroBH04/abrasel-monitor-legislativo.git
cd abrasel-monitor-legislativo

# 2. Ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Instalar dependências
pip install -e ".[dev]"

# 4. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais

# 5. Subir serviços locais (PostgreSQL + LocalStack)
docker-compose up -d postgres redis localstack

# 6. Rodar migrations
alembic upgrade head

# 7. Testar
pytest tests/ -v
```

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://abrasel:abrasel@localhost:5432/monitor_legislativo` |
| `S3_BUCKET_BRONZE` | Bucket Bronze | `abrasel-monitor-bronze` |
| `S3_BUCKET_SILVER` | Bucket Silver | `abrasel-monitor-silver` |
| `SLACK_WEBHOOK_URL` | Webhook do canal Slack | *(obrigatório para alertas)* |
| `SES_SENDER_EMAIL` | Email remetente (SES verificado) | `monitor@abrasel.com.br` |
| `SES_RECIPIENT_EMAILS` | Emails destinatários (vírgula) | *(configurar)* |
| `CAMARA_RATE_LIMIT_RPS` | Req/seg para API da Câmara | `1.0` |
| `SENADO_RATE_LIMIT_RPS` | Req/seg para API do Senado | `1.0` |
| `ANTHROPIC_API_KEY` | Chave API Anthropic (mcp-brasil) | *(opcional)* |

---

## Uso (CLI)

```bash
# Coleta incremental de uma fonte
abrasel-monitor collect camara --mode incremental
abrasel-monitor collect senado --mode incremental

# Carga histórica completa desde 1988
abrasel-monitor full-load --ano-inicio 1988 --sources camara,senado

# Pipeline completo de um ano (coleta + scoring + gold)
abrasel-monitor pipeline camara --ano 2024

# Reprocessar scoring de todas as proposições
abrasel-monitor score

# Recalcular índice de alinhamento parlamentar
abrasel-monitor alignment

# Verificar e disparar alertas pendentes
abrasel-monitor alerts

# Iniciar dashboard local
abrasel-monitor dashboard

# Status geral do sistema
abrasel-monitor status
```

---

## Agendamento Automático (Produção)

| Job | Horário | Descrição |
|-----|---------|-----------|
| Coleta Incremental | Diário 06h00 | Novas proposições de todas as fontes |
| Varredura de Agenda | Diário 07h00 | Pauta dos próximos 3 dias + alertas |
| Varredura Express | A cada 4h (dias úteis) | Votações em andamento |
| Atualização Parlamentares | Diário 05h00 | Recalcula índices de alinhamento |
| Relatório Semanal | Sexta 18h00 | Email com resumo da semana |

---

## Dashboard

O protótipo Streamlit oferece 6 páginas:

1. **Visão Geral** — métricas principais, gráficos de relevância e evolução mensal
2. **Proposições** — busca e filtro por relevância, tipo, situação e período
3. **Parlamentares** — ranking de aliados, índice de alinhamento e distribuição por classificação
4. **Agenda e Alertas** — próximas votações críticas e histórico de alertas disparados
5. **Relatórios** — geração e download de relatórios semanais/mensais em CSV
6. **Configuração** — status das fontes de dados e keywords ativas

```bash
# Iniciar localmente
abrasel-monitor dashboard
# Acesse: http://localhost:8501
```

Em produção, o dashboard será migrado para **Metabase** (self-hosted no ECS), com acesso por SSO corporativo.

---

## Infraestrutura AWS

```
Custo estimado: < R$ 800/mês
Região: sa-east-1 (São Paulo)
```

| Serviço | Uso | Custo/mês |
|---------|-----|-----------|
| ECS Fargate | Tasks periódicas (collectors) | ~R$ 80 |
| RDS PostgreSQL `db.t4g.micro` | Gold Layer | ~R$ 150 |
| S3 (Bronze + Silver) | ~500 GB/ano | ~R$ 50 |
| DynamoDB | Checkpoints (PAY_PER_REQUEST) | ~R$ 5 |
| EventBridge Scheduler | 5 schedules | < R$ 5 |
| SES | ~200 emails/mês | < R$ 5 |
| CloudWatch Logs | 30 dias retenção | ~R$ 20 |

### Deploy

```bash
# Provisionar infraestrutura
cd terraform
terraform init
terraform plan -var="db_password=SENHA_SEGURA"
terraform apply

# Build e push da imagem
docker build -t abrasel-monitor-legislativo .
aws ecr get-login-password --region sa-east-1 | docker login --username AWS --password-stdin <ECR_URL>
docker push <ECR_URL>/abrasel-monitor-legislativo:latest

# Rodar migrations em produção
abrasel-monitor pipeline camara --ano 2024  # teste inicial
```

---

## Testes

```bash
# Todos os testes
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=abrasel_monitor --cov-report=html

# Apenas testes do scoring
pytest tests/test_scoring.py -v

# Lint e type check
ruff check src/
mypy src/abrasel_monitor/
```

### Cobertura por módulo

| Módulo | Testes |
|--------|--------|
| `scoring/engine.py` | Keywords match, pesos, exclusões, batch |
| `collectors/camara.py` | Parse de proposição, paginação |
| `collectors/senado.py` | Extração de matérias, safe_int |
| `parlamentares/alignment.py` | Todos os limiares de classificação |

---

## Integração com mcp-brasil

O projeto usa o pacote [`mcp-brasil`](https://github.com/jxnxts/mcp-brasil) como dependência para acesso via MCP tools às APIs brasileiras. Isso permite que agentes de IA (como Claude) consultem dados legislativos em linguagem natural:

```python
# Exemplo: recomendar ferramentas via mcp-brasil
from mcp_brasil import listar_features, recomendar_tools

# Descobrir tools disponíveis para pesquisa legislativa
tools = await recomendar_tools("proposições sobre restaurantes e alimentação")
```

Os coletores próprios do monitor são usados para controle fino de rate limiting, checkpointing e persistência S3 — o mcp-brasil complementa com discovery inteligente e acesso rápido para consultas ad-hoc.

---

## Roadmap

### v1.0 — MVP (atual)
- [x] Coletores: Câmara + Senado + 9 Assembleias
- [x] Pipeline ETL completo (Bronze → Silver → Gold)
- [x] Motor de scoring por keywords + temas
- [x] Alertas Slack + Email
- [x] Dashboard Streamlit (protótipo)
- [x] Infraestrutura AWS (Terraform)

### v1.1 — Consolidação
- [ ] Migração dashboard para Metabase
- [ ] Carga histórica completa desde 1988
- [ ] Testes de integração end-to-end
- [ ] Monitoramento com CloudWatch Dashboards

### v2.0 — Inteligência
- [ ] NLP para resumo automático de proposições (Claude API)
- [ ] Detecção de similaridade entre proposições (embeddings)
- [ ] Análise de impacto financeiro por proposta
- [ ] Expansão para Câmaras Municipais (SP, RJ, BH, POA, Curitiba)

---

## Licença

Uso interno Abrasel — todos os direitos reservados.

---

<div align="center">
  <strong>Abrasel — Associação Brasileira de Bares e Restaurantes</strong><br>
  Monitor Legislativo v1.0 — Equipe de Dados e Relações Institucionais
</div>
