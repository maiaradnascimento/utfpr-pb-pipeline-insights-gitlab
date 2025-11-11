"""
CLI para ETL Incremental

Uso:
    python src/cli/etl_incremental.py [--reprocess-days 3]
"""

import os
import sys
import argparse
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.etl.incremental import IncrementalETL


def main():
    parser = argparse.ArgumentParser(description="Executa ETL incremental")
    parser.add_argument("--reprocess-days", type=int, default=3,
                       help="Dias para reprocessar (janela deslizante). Use 0 ou valor muito grande para processar tudo.")
    parser.add_argument("--process-all", action="store_true",
                       help="Processa todos os dados disponíveis (sem limite de dias)")
    parser.add_argument("--db-url", type=str, default=None,
                       help="URL do banco PostgreSQL")
    
    args = parser.parse_args()
    
    db_url = args.db_url or os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
    )
    
    # Se --process-all, usa 0 para indicar "processar tudo"
    # Se --reprocess-days >= 10000, também processa tudo
    if args.process_all or args.reprocess_days >= 10000:
        reprocess_days = 0  # 0 indica processar tudo
    else:
        reprocess_days = args.reprocess_days
    
    with IncrementalETL(db_url) as etl:
        etl.run(reprocess_window_days=reprocess_days)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

