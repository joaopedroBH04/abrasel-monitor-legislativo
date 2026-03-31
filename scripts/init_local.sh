#!/bin/bash
# Script de inicializacao do ambiente local de desenvolvimento
# Uso: bash scripts/init_local.sh

set -e

echo "=== Abrasel Monitor Legislativo - Setup Local ==="

# 1. Criar ambiente virtual
echo "Criando ambiente virtual..."
python -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
echo "Instalando dependencias..."
pip install --upgrade pip
pip install -e ".[dev]"

# 3. Subir servicos Docker
echo "Subindo PostgreSQL, Redis e LocalStack..."
docker-compose up -d postgres redis localstack

# 4. Aguardar PostgreSQL
echo "Aguardando PostgreSQL..."
until docker-compose exec postgres pg_isready -U abrasel -d monitor_legislativo 2>/dev/null; do
    sleep 1
done

# 5. Rodar migrations
echo "Rodando migrations..."
cp .env.example .env
alembic upgrade head || echo "Migrations pendentes - rode 'alembic revision --autogenerate' primeiro"

# 6. Criar buckets S3 no LocalStack
echo "Criando buckets S3 no LocalStack..."
aws --endpoint-url=http://localhost:4566 s3 mb s3://abrasel-monitor-bronze 2>/dev/null || true
aws --endpoint-url=http://localhost:4566 s3 mb s3://abrasel-monitor-silver 2>/dev/null || true

# 7. Criar tabela DynamoDB no LocalStack
echo "Criando tabela DynamoDB..."
aws --endpoint-url=http://localhost:4566 dynamodb create-table \
    --table-name abrasel-monitor-checkpoints \
    --attribute-definitions AttributeName=source,AttributeType=S AttributeName=checkpoint_key,AttributeType=S \
    --key-schema AttributeName=source,KeyType=HASH AttributeName=checkpoint_key,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST 2>/dev/null || true

echo ""
echo "=== Setup concluido! ==="
echo "Comandos disponiveis:"
echo "  abrasel-monitor status          # Ver status do sistema"
echo "  abrasel-monitor collect camara   # Coletar dados da Camara"
echo "  abrasel-monitor dashboard        # Iniciar dashboard"
echo "  pytest tests/ -v                 # Rodar testes"
