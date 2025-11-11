"""
Training Script - Treina modelo e registra versão

Uso:
    python src/ml/train.py --window-start 2025-01-01 --window-end 2025-12-31
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ml.registry import ModelRegistry
from src.core.config import Config
import psycopg2
from sqlalchemy import create_engine, text


def load_training_features(db_url: str, window_start: str = None, window_end: str = None) -> pd.DataFrame:
    """
    Carrega features offline para treino
    
    Args:
        db_url: URL do banco
        window_start: Data início (YYYY-MM-DD) ou None para todos os dados
        window_end: Data fim (YYYY-MM-DD) ou None para todos os dados
    
    Returns:
        DataFrame com features
    """
    # Usa SQLAlchemy para evitar warning do pandas
    engine = create_engine(db_url)
    
    if window_start is None or window_end is None:
        # Carrega todos os dados
        query = text("""
        SELECT
            entity_key,
            payload,
            event_time
        FROM features_offline
        ORDER BY event_time
        """)
        df = pd.read_sql_query(query, engine)
    else:
        # Converte strings para datetime antes de passar para a query
        from datetime import datetime as dt
        window_start_dt = dt.strptime(window_start, '%Y-%m-%d')
        window_end_dt = dt.strptime(window_end, '%Y-%m-%d')
        
        query = text("""
        SELECT
            entity_key,
            payload,
            event_time
        FROM features_offline
        WHERE event_time >= :window_start
          AND event_time < :window_end + INTERVAL '1 day'
        ORDER BY event_time
        """)
        
        df = pd.read_sql_query(query, engine, params={'window_start': window_start_dt, 'window_end': window_end_dt})
    
    engine.dispose()
    
    if df.empty:
        return df
    
    # Expande payload JSONB
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
    
    return features_df


def train_model(df: pd.DataFrame) -> tuple:
    """
    Treina modelo Isolation Forest
    
    Args:
        df: DataFrame com features
    
    Returns:
        (model, scaler, metrics)
    """
    # Features
    feature_cols = ['dur_total', 'stage_build', 'stage_test', 'stage_deploy', 'fail_rate', 'max_retries']
    feature_cols = [c for c in feature_cols if c in df.columns]
    
    if len(feature_cols) == 0:
        raise ValueError("Nenhuma feature encontrada")
    
    X = df[feature_cols].fillna(0).values
    
    # Normalização
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Treina Isolation Forest
    model = IsolationForest(
        contamination=Config.ML_CONTAMINATION,
        random_state=Config.ML_RANDOM_STATE,
        n_estimators=200
    )
    
    model.fit(X_scaled)
    
    # Predições para métricas
    predictions = model.predict(X_scaled)
    scores = model.score_samples(X_scaled)
    
    # Métricas (usando threshold adaptativo)
    threshold = np.percentile(scores, (1 - Config.ML_CONTAMINATION) * 100)
    y_pred = (scores < threshold).astype(int)
    
    # Se tiver labels reais, calcula métricas
    # Por enquanto, apenas estatísticas básicas
    metrics = {
        'n_samples': len(df),
        'n_features': len(feature_cols),
        'contamination': Config.ML_CONTAMINATION,
        'n_anomalies_detected': int((predictions == -1).sum()),
        'anomaly_rate': float((predictions == -1).mean()),
        'score_mean': float(scores.mean()),
        'score_std': float(scores.std()),
        'score_min': float(scores.min()),
        'score_max': float(scores.max()),
        'threshold': float(threshold)
    }
    
    return model, scaler, metrics, feature_cols


def main():
    parser = argparse.ArgumentParser(description="Treina modelo ML")
    parser.add_argument("--window-start", type=str, default=None,
                       help="Data início treino (YYYY-MM-DD). Se não fornecido e --all não usado, usa 180 dias atrás.")
    parser.add_argument("--window-end", type=str, default=None,
                       help="Data fim treino (YYYY-MM-DD). Se não fornecido e --all não usado, usa hoje.")
    parser.add_argument("--all", action="store_true",
                       help="Treina com todos os dados disponíveis (ignora window-start e window-end)")
    parser.add_argument("--db-url", type=str, default=None,
                       help="URL do banco PostgreSQL")
    
    args = parser.parse_args()
    
    # Configurações
    db_url = args.db_url or os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
    )
    
    # Determina janela de treino
    if args.all:
        window_start = None
        window_end = None
        print("🎓 Iniciando treino do modelo...")
        print("   Modo: TODOS os dados disponíveis")
    else:
        window_start = args.window_start or (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        window_end = args.window_end or datetime.now().strftime("%Y-%m-%d")
        print("🎓 Iniciando treino do modelo...")
        print(f"   Janela: {window_start} a {window_end}")
    print()
    
    # 1. Carrega features
    print("📥 Carregando features offline...")
    df = load_training_features(db_url, window_start, window_end)
    
    if df.empty:
        print("❌ Nenhuma feature encontrada na janela especificada")
        return 1
    
    print(f"   ✅ {len(df)} registros carregados")
    print()
    
    # 2. Treina modelo
    print("🔄 Treinando modelo...")
    try:
        model, scaler, metrics, feature_cols = train_model(df)
        print(f"   ✅ Modelo treinado com sucesso")
        print(f"   📊 Métricas:")
        for k, v in metrics.items():
            print(f"      {k}: {v}")
    except Exception as e:
        print(f"   ❌ Erro no treino: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print()
    
    # 3. Salva modelo e transformadores
    registry = ModelRegistry(db_url)
    new_version = registry.bump_model_version()
    
    print(f"💾 Salvando modelo v{new_version}...")
    registry.save_model(model, new_version)
    registry.save_transformer(scaler, new_version, "scaler")
    
    # 4. Salva feature schema
    feature_schema = {
        'version': new_version,
        'features': feature_cols,
        'order': feature_cols,
        'dtypes': {col: 'float64' for col in feature_cols},
        'transforms': {col: 'standard_scaler' for col in feature_cols}
    }
    registry.save_feature_schema(feature_schema, new_version)
    
    # 5. Registra no banco
    print(f"📝 Registrando modelo v{new_version} no banco...")
    
    # Obtém feature_version atual do banco
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM kv_config WHERE key = 'FEATURE_VERSION_CURRENT'")
        row = cur.fetchone()
        feature_version = int(row[0]) if row else 1
    conn.close()
    
    registry.register_model(
        version=new_version,
        feature_version=feature_version,
        model_type="isolation_forest",
        training_window_start=args.window_start,
        training_window_end=args.window_end,
        metrics=metrics,
        trained_by="train.py"
    )
    
    print()
    print("✅ Treino concluído!")
    print(f"   Modelo v{new_version} está em produção")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

