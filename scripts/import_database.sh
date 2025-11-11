#!/bin/bash
set -e

# Script para importar banco de dados
# Uso: ./scripts/import_database.sh [arquivo.sql.gz]

INPUT_FILE=${1:-"database_backup.sql.gz"}
DB_NAME=${DB_NAME:-pipeline_optimizer}
DB_USER=${DB_USER:-postgres}
DB_PASS=${DB_PASS:-postgres}

if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ Arquivo não encontrado: $INPUT_FILE"
    exit 1
fi

echo "📥 Importando banco de dados..."
echo "   Arquivo: $INPUT_FILE"
echo "   Banco: $DB_NAME"

# Importa via Docker
if docker ps | grep -q pipeline-optimizer-postgres; then
    echo "✅ Usando container Docker..."
    gunzip -c "$INPUT_FILE" | docker exec -i pipeline-optimizer-postgres psql -U $DB_USER -d $DB_NAME
else
    echo "❌ Container Docker não está rodando!"
    echo "   Execute: make up ou docker-compose up -d postgres"
    exit 1
fi

echo ""
echo "✅ Banco importado com sucesso!"

