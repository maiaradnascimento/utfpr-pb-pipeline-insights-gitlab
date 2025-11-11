"""
FastAPI Application - REST endpoints para predições e métricas
"""

import os
import sys
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd
import psycopg2
from psycopg2.extras import Json

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ml.registry import ModelRegistry
from src.core.config import Config

app = FastAPI(title="Pipeline Optimizer API", version="1.0.0")


# ================================================================
# MODELS
# ================================================================

class PredictionResponse(BaseModel):
    run_id: str
    model_version: int
    feature_version: int
    prediction: Dict[str, Any]
    score: Optional[float]
    label: str
    created_at: datetime


class PredictionRequest(BaseModel):
    run_id: str
    entity_key: Optional[str] = None


# ================================================================
# DATABASE
# ================================================================

def get_db_conn():
    """Retorna conexão com banco"""
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
    )
    return psycopg2.connect(db_url)


# ================================================================
# ENDPOINTS
# ================================================================

@app.get("/healthz")
def healthz():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/predictions")
def get_predictions(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    mode: str = Query("actual", regex="^(actual|snapshot)$"),
    model_version: Optional[int] = Query(None)
):
    """
    Busca predições com filtros
    
    Args:
        from_date: Data início (YYYY-MM-DD)
        to_date: Data fim (YYYY-MM-DD)
        mode: 'actual' (modelo atual) ou 'snapshot' (versão fixa)
        model_version: Versão do modelo (obrigatório se mode=snapshot)
    
    Returns:
        Lista de predições
    """
    conn = get_db_conn()
    
    try:
        registry = ModelRegistry()
        
        # Determina versão do modelo
        if mode == "actual":
            model_ver = registry.current_model_version()
        elif mode == "snapshot":
            if model_version is None:
                raise HTTPException(status_code=400, detail="model_version obrigatório em modo snapshot")
            model_ver = model_version
        else:
            raise HTTPException(status_code=400, detail="mode deve ser 'actual' ou 'snapshot'")
        
        # Query
        query = """
        SELECT 
            run_id, model_version, feature_version,
            prediction, score, label, created_at
        FROM predictions
        WHERE model_version = %s
        """
        params = [model_ver]
        
        if from_date:
            query += " AND created_at >= %s::date"
            params.append(from_date)
        
        if to_date:
            query += " AND created_at < (%s::date + INTERVAL '1 day')"
            params.append(to_date)
        
        query += " ORDER BY created_at DESC LIMIT 1000"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        # Converte para JSON
        predictions = []
        for _, row in df.iterrows():
            predictions.append({
                "run_id": row['run_id'],
                "model_version": int(row['model_version']),
                "feature_version": int(row['feature_version']),
                "prediction": row['prediction'] if isinstance(row['prediction'], dict) else {},
                "score": float(row['score']) if pd.notna(row['score']) else None,
                "label": row['label'],
                "created_at": row['created_at'].isoformat() if pd.notna(row['created_at']) else None
            })
        
        return {
            "mode": mode,
            "model_version": model_ver,
            "count": len(predictions),
            "predictions": predictions
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/infer/{run_id}")
def infer_run(run_id: str, request: Optional[PredictionRequest] = None):
    """
    Gera predição para um run_id
    
    Args:
        run_id: ID da execução
        request: Opcional, pode conter entity_key
    
    Returns:
        Predição
    """
    conn = get_db_conn()
    registry = ModelRegistry()
    
    try:
        # Determina entity_key
        entity_key = request.entity_key if request else None
        if not entity_key:
            # Tenta construir do run_id (formato: project_id:job_name)
            entity_key = run_id
        
        # Busca features no cache (features_online)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload, feature_version FROM features_online WHERE entity_key = %s",
                (entity_key,)
            )
            row = cur.fetchone()
            
            if not row:
                # Se não existe, tenta gerar on-the-fly (simplificado)
                raise HTTPException(
                    status_code=404,
                    detail=f"Features não encontradas para entity_key={entity_key}. Execute ETL primeiro."
                )
            
            payload, feature_version = row
        
        # Carrega modelo atual
        model_version = registry.current_model_version()
        model = registry.load_model(model_version)
        scaler = registry.load_transformer(model_version, "scaler")
        schema = registry.load_feature_schema(model_version)
        
        # Prepara features
        feature_cols = schema.get('features', [])
        X = [[payload.get(col, 0.0) for col in feature_cols]]
        X_scaled = scaler.transform(X)
        
        # Predição
        prediction = model.predict(X_scaled)[0]
        score = model.score_samples(X_scaled)[0]
        
        label = "anomaly" if prediction == -1 else "normal"
        
        prediction_data = {
            "anomaly": int(prediction == -1),
            "score": float(score),
            "features": {col: float(X[0][i]) for i, col in enumerate(feature_cols)}
        }
        
        # Salva predição (ON CONFLICT DO NOTHING)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO predictions (
                    run_id, model_version, feature_version, prediction, score, label
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (run_id, model_version) DO NOTHING
                """,
                (run_id, model_version, feature_version, Json(prediction_data), float(score), label)
            )
            conn.commit()
        
        conn.close()
        
        return {
            "run_id": run_id,
            "model_version": model_version,
            "feature_version": feature_version,
            "prediction": prediction_data,
            "score": float(score),
            "label": label,
            "calc_ts": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predictions/generate")
def generate_predictions_batch():
    """
    Gera predições em lote para todas as features_online disponíveis
    e salva na tabela predictions
    """
    conn = get_db_conn()
    registry = ModelRegistry()
    
    try:
        # Carrega modelo atual
        model_version = registry.current_model_version()
        model = registry.load_model(model_version)
        scaler = registry.load_transformer(model_version, "scaler")
        schema = registry.load_feature_schema(model_version)
        
        # Busca todas as features_online
        query = """
        SELECT entity_key, payload, feature_version, updated_at
        FROM features_online
        ORDER BY updated_at DESC
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            conn.close()
            return {
                "status": "ok",
                "message": "Nenhuma feature encontrada",
                "count": 0
            }
        
        feature_cols = schema.get('features', [])
        count = 0
        errors = 0
        
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                try:
                    entity_key = row['entity_key']
                    payload = row['payload']
                    feature_version = row['feature_version']
                    
                    # Prepara features
                    X = [[payload.get(col, 0.0) for col in feature_cols]]
                    X_scaled = scaler.transform(X)
                    
                    # Predição
                    prediction = model.predict(X_scaled)[0]
                    score = model.score_samples(X_scaled)[0]
                    
                    label = "anomaly" if prediction == -1 else "normal"
                    
                    prediction_data = {
                        "anomaly": int(prediction == -1),
                        "score": float(score),
                        "features": {col: float(X[0][i]) for i, col in enumerate(feature_cols)}
                    }
                    
                    # Salva predição (ON CONFLICT DO NOTHING)
                    cur.execute(
                        """
                        INSERT INTO predictions (
                            run_id, model_version, feature_version, prediction, score, label
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                        ON CONFLICT (run_id, model_version) DO NOTHING
                        """,
                        (entity_key, model_version, feature_version, Json(prediction_data), float(score), label)
                    )
                    count += 1
                except Exception as e:
                    errors += 1
                    continue
            
            conn.commit()
        
        conn.close()
        
        return {
            "status": "ok",
            "message": f"Geradas {count} predições",
            "count": count,
            "errors": errors,
            "model_version": model_version
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def get_metrics(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    project_id: Optional[int] = Query(None)
):
    """
    Busca métricas diárias
    
    Args:
        from_date: Data início (YYYY-MM-DD)
        to_date: Data fim (YYYY-MM-DD)
        project_id: ID do projeto (None = usa Config.PROJECT_ID)
    
    Returns:
        Lista de métricas
    """
    conn = get_db_conn()
    
    try:
        proj_id = project_id or Config.PROJECT_ID
        
        query = """
        SELECT 
            project_id, job_name, day,
            builds, fails, p95_duration, avg_duration, max_retries
        FROM metrics_daily
        WHERE project_id = %s
        """
        params = [proj_id]
        
        if from_date:
            query += " AND day >= %s"
            params.append(from_date)
        
        if to_date:
            query += " AND day <= %s"
            params.append(to_date)
        
        query += " ORDER BY day DESC, job_name LIMIT 1000"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        metrics = []
        for _, row in df.iterrows():
            metrics.append({
                "project_id": int(row['project_id']),
                "job_name": row['job_name'],
                "day": row['day'].isoformat() if pd.notna(row['day']) else None,
                "builds": int(row['builds']) if pd.notna(row['builds']) else 0,
                "fails": int(row['fails']) if pd.notna(row['fails']) else 0,
                "p95_duration": float(row['p95_duration']) if pd.notna(row['p95_duration']) else None,
                "avg_duration": float(row['avg_duration']) if pd.notna(row['avg_duration']) else None,
                "max_retries": int(row['max_retries']) if pd.notna(row['max_retries']) else 0
            })
        
        return {
            "count": len(metrics),
            "metrics": metrics
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/errors")
def get_errors(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    project_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Busca erros de pipelines/jobs
    
    Args:
        from_date: Data início (YYYY-MM-DD)
        to_date: Data fim (YYYY-MM-DD)
        project_id: ID do projeto (None = usa Config.PROJECT_ID)
        limit: Limite de resultados (padrão 100, máximo 1000)
    
    Returns:
        Lista de erros com detalhes
    """
    conn = get_db_conn()
    
    try:
        proj_id = project_id or Config.PROJECT_ID
        
        query = """
        SELECT 
            j.id as job_id,
            j.pipeline_id,
            j.name as job_name,
            j.stage,
            j.status,
            j.failure_reason,
            j.retry_count,
            j.web_url as job_url,
            j.created_at,
            j.finished_at,
            p.web_url as pipeline_url,
            p.status as pipeline_status
        FROM jobs_raw j
        LEFT JOIN pipelines_raw p ON j.pipeline_id = p.id
        WHERE j.project_id = %s
          AND j.status = 'failed'
          AND j.failure_reason IS NOT NULL
        """
        params = [proj_id]
        
        if from_date:
            query += " AND j.created_at >= %s::date"
            params.append(from_date)
        
        if to_date:
            query += " AND j.created_at < (%s::date + INTERVAL '1 day')"
            params.append(to_date)
        
        query += " ORDER BY j.created_at DESC LIMIT %s"
        params.append(limit)
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        errors = []
        for _, row in df.iterrows():
            errors.append({
                "job_id": int(row['job_id']) if pd.notna(row['job_id']) else None,
                "pipeline_id": int(row['pipeline_id']) if pd.notna(row['pipeline_id']) else None,
                "job_name": row['job_name'],
                "stage": row['stage'] if pd.notna(row['stage']) else None,
                "status": row['status'],
                "failure_reason": row['failure_reason'] if pd.notna(row['failure_reason']) else None,
                "retry_count": int(row['retry_count']) if pd.notna(row['retry_count']) else 0,
                "job_url": row['job_url'] if pd.notna(row['job_url']) else None,
                "pipeline_url": row['pipeline_url'] if pd.notna(row['pipeline_url']) else None,
                "pipeline_status": row['pipeline_status'] if pd.notna(row['pipeline_status']) else None,
                "created_at": row['created_at'].isoformat() if pd.notna(row['created_at']) else None,
                "finished_at": row['finished_at'].isoformat() if pd.notna(row['finished_at']) else None
            })
        
        return {
            "count": len(errors),
            "errors": errors
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/errors/summary")
def get_errors_summary(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    project_id: Optional[int] = Query(None)
):
    """
    Retorna resumo de erros agregados por tipo
    
    Args:
        from_date: Data início (YYYY-MM-DD)
        to_date: Data fim (YYYY-MM-DD)
        project_id: ID do projeto (None = usa Config.PROJECT_ID)
    
    Returns:
        Resumo de erros por tipo, job, etc.
    """
    conn = get_db_conn()
    
    try:
        proj_id = project_id or Config.PROJECT_ID
        
        query = """
        SELECT 
            job_name,
            error_types,
            SUM(fails) as total_fails,
            SUM(builds) as total_builds
        FROM metrics_daily
        WHERE project_id = %s
          AND fails > 0
        """
        params = [proj_id]
        
        if from_date:
            query += " AND day >= %s"
            params.append(from_date)
        
        if to_date:
            query += " AND day <= %s"
            params.append(to_date)
        
        query += " GROUP BY job_name, error_types ORDER BY total_fails DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        summary = []
        for _, row in df.iterrows():
            error_types = row['error_types']
            if isinstance(error_types, str):
                try:
                    error_types = json.loads(error_types)
                except:
                    error_types = {}
            elif not isinstance(error_types, dict):
                error_types = {}
            
            summary.append({
                "job_name": row['job_name'],
                "total_fails": int(row['total_fails']) if pd.notna(row['total_fails']) else 0,
                "total_builds": int(row['total_builds']) if pd.notna(row['total_builds']) else 0,
                "error_types": error_types,
                "fail_rate": float(row['total_fails'] / row['total_builds'] * 100) if pd.notna(row['total_builds']) and row['total_builds'] > 0 else 0.0
            })
        
        return {
            "count": len(summary),
            "summary": summary
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model/info")
def get_model_info():
    """Retorna informações do modelo atual"""
    conn = get_db_conn()
    registry = ModelRegistry()
    
    try:
        model_version = registry.current_model_version()
        
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    model_version, feature_version, model_type,
                    training_window_start, training_window_end,
                    metrics, created_at
                FROM model_registry
                WHERE model_version = %s
                """,
                (model_version,)
            )
            row = cur.fetchone()
        
        conn.close()
        
        if not row:
            return {
                "model_version": model_version,
                "status": "not_registered"
            }
        
        return {
            "model_version": int(row[0]),
            "feature_version": int(row[1]),
            "model_type": row[2],
            "training_window_start": row[3].isoformat() if row[3] else None,
            "training_window_end": row[4].isoformat() if row[4] else None,
            "metrics": row[5] if isinstance(row[5], dict) else {},
            "created_at": row[6].isoformat() if row[6] else None
        }
    
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

