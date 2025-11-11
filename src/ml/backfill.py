"""
Backfill Script - Re-scora predições históricas

Uso:
    python src/ml/backfill.py --model-version 2 --days 30
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ml.registry import ModelRegistry
import psycopg2
from psycopg2.extras import Json


def backfill_predictions(db_url: str, model_version: int, days: int = 30):
    """
    Re-scora predições dos últimos N dias e salva em predictions_backfill
    
    Args:
        db_url: URL do banco
        model_version: Versão do modelo a usar
        days: Número de dias para backfill
    """
    # Usa SQLAlchemy para evitar warnings do pandas
    engine = create_engine(db_url)
    
    # Para operações que precisam de psycopg2 (INSERT com Json)
    conn = psycopg2.connect(db_url)
    
    # Carrega modelo
    registry = ModelRegistry(db_url)
    model = registry.load_model(model_version)
    scaler = registry.load_transformer(model_version, "scaler")
    schema = registry.load_feature_schema(model_version)
    
    # Data limite
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Converte para datetime para SQLAlchemy
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time())
    
    print(f"🔄 Executando backfill com modelo v{model_version}...")
    print(f"   Janela: {start_date} a {end_date}")
    print()
    
    # Busca features offline da janela usando SQLAlchemy
    query = text("""
    SELECT 
        entity_key,
        payload,
        event_time
    FROM features_offline
    WHERE event_time >= :start_date
      AND event_time < :end_date + INTERVAL '1 day'
    ORDER BY event_time
    """)
    
    df = pd.read_sql_query(
        query, 
        engine, 
        params={'start_date': start_datetime, 'end_date': end_datetime}
    )
    
    if df.empty:
        print("   ℹ️  Nenhuma feature encontrada")
        conn.close()
        engine.dispose()
        return 0
    
    print(f"   ✅ {len(df)} features encontradas")
    
    # Expande payload
    features_list = []
    for _, row in df.iterrows():
        payload = row['payload']
        if isinstance(payload, dict):
            features_list.append(payload)
        else:
            features_list.append({})
    
    features_df = pd.DataFrame(features_list)
    features_df['entity_key'] = df['entity_key']
    features_df['event_time'] = df['event_time']
    
    # Prepara features conforme schema
    feature_cols = schema.get('features', [])
    feature_cols = [c for c in feature_cols if c in features_df.columns]
    
    if len(feature_cols) == 0:
        print("   ❌ Nenhuma feature válida encontrada")
        conn.close()
        engine.dispose()
        return 1
    
    X = features_df[feature_cols].fillna(0).values
    X_scaled = scaler.transform(X)
    
    # Predições
    predictions = model.predict(X_scaled)
    scores = model.score_samples(X_scaled)
    
    # Salva em predictions_backfill
    with conn.cursor() as cur:
        count = 0
        for idx, row in features_df.iterrows():
            entity_key = row['entity_key']
            run_id = entity_key  # Usa entity_key como run_id
            
            prediction_data = {
                'anomaly': int(predictions[idx] == -1),
                'score': float(scores[idx]),
                'features': {col: float(X[idx, feature_cols.index(col)]) for col in feature_cols}
            }
            
            label = "anomaly" if predictions[idx] == -1 else "normal"
            
            cur.execute(
                """
                INSERT INTO predictions_backfill (
                    run_id, model_version, feature_version, prediction, score, label
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (run_id, model_version) DO NOTHING
                """,
                (
                    run_id,
                    model_version,
                    schema['version'],
                    Json(prediction_data),
                    float(scores[idx]),
                    label
                )
            )
            count += 1
        
        conn.commit()
    
    conn.close()
    engine.dispose()
    
    print(f"   ✅ {count} predições salvas em predictions_backfill")
    print()
    print("✅ Backfill concluído!")
    
    return count


def main():
    parser = argparse.ArgumentParser(description="Backfill de predições históricas")
    parser.add_argument("--model-version", type=int, default=None,
                       help="Versão do modelo (None = atual)")
    parser.add_argument("--days", type=int, default=30,
                       help="Número de dias para backfill")
    parser.add_argument("--db-url", type=str, default=None,
                       help="URL do banco PostgreSQL")
    
    args = parser.parse_args()
    
    db_url = args.db_url or os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
    )
    
    registry = ModelRegistry(db_url)
    model_version = args.model_version or registry.current_model_version()
    
    count = backfill_predictions(db_url, model_version, args.days)
    
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

