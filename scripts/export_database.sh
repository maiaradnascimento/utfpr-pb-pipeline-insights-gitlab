#!/bin/bash
set -e

# Script para exportar banco de dados para distribuição
# Uso: ./scripts/export_database.sh [nome_do_arquivo]

OUTPUT_FILE=${1:-"database_backup_$(date +%Y%m%d_%H%M%S).sql.gz"}
DB_NAME=${DB_NAME:-pipeline_optimizer}
DB_USER=${DB_USER:-postgres}
DB_PASS=${DB_PASS:-postgres}
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}

echo "📦 Exportando banco de dados..."
echo "   Banco: $DB_NAME"
echo "   Arquivo: $OUTPUT_FILE"

# Exporta via Docker se estiver rodando
if docker ps | grep -q pipeline-optimizer-postgres; then
    echo "✅ Usando container Docker..."
    docker exec pipeline-optimizer-postgres pg_dump -U $DB_USER -d $DB_NAME | gzip > "$OUTPUT_FILE"
else
    echo "✅ Usando conexão local..."
    PGPASSWORD=$DB_PASS pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME | gzip > "$OUTPUT_FILE"
fi

echo ""
echo "✅ Banco exportado com sucesso!"
echo "   Arquivo: $OUTPUT_FILE"
echo "   Tamanho: $(du -h "$OUTPUT_FILE" | cut -f1)"

