"""
ETL Incremental - Processamento Idempotente com Watermark

Regras:
- Raw é append-only (nunca sobrescreve)
- Watermark por fonte (último timestamp processado)
- Upsert idempotente nos agregados/features (chaves naturais)
- Janelas deslizantes (7/30d); reocupa apenas a janela corrente
- Predições: gravar por (run_id, model_version) e não alterar
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np
import json
import psycopg2
from psycopg2.extras import execute_values, Json
from psycopg2.extensions import register_adapter, AsIs

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config import Config

# Registra adaptador JSON para psycopg2
register_adapter(dict, Json)
register_adapter(list, Json)


class IncrementalETL:
    """ETL Incremental com watermark e upsert idempotente"""
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Inicializa ETL com conexão PostgreSQL
        
        Args:
            db_url: URL de conexão PostgreSQL (ex: postgresql://user:pass@host/db)
                     Se None, usa variáveis de ambiente padrão
        """
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
        )
        self.conn = None
        self.stats = {
            'rows_read': 0,
            'rows_processed': 0,
            'rows_written': 0,
            'window_reprocessed': False,
            'last_ts': None,
            'duration_sec': 0
        }
    
    def connect(self):
        """Abre conexão com PostgreSQL"""
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(self.db_url)
        return self.conn
    
    def close(self):
        """Fecha conexão"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # ================================================================
    # WATERMARK MANAGEMENT
    # ================================================================
    
    def get_watermark(self, source: str) -> Optional[datetime]:
        """
        Obtém último timestamp processado para uma fonte
        
        Args:
            source: Nome da fonte (ex: 'pipelines', 'jobs')
        
        Returns:
            datetime ou None se nunca processado (sempre retorna UTC-aware)
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT last_ts FROM processing_watermarks WHERE source = %s",
                (source,)
            )
            row = cur.fetchone()
            if row:
                ts = row[0]
                # Normaliza para UTC-aware
                if isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        # Se é naive, assume UTC
                        ts = ts.replace(tzinfo=timezone.utc)
                    else:
                        # Se já tem timezone, converte para UTC
                        ts = ts.astimezone(timezone.utc)
                return ts
            return None
    
    def update_watermark(self, source: str, last_ts: datetime):
        """
        Atualiza watermark para uma fonte
        
        Args:
            source: Nome da fonte
            last_ts: Último timestamp processado
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processing_watermarks (source, last_ts)
                VALUES (%s, %s)
                ON CONFLICT (source) DO UPDATE
                SET last_ts = EXCLUDED.last_ts, updated_at = CURRENT_TIMESTAMP
                """,
                (source, last_ts)
            )
            self.conn.commit()
    
    # ================================================================
    # RAW DATA LOADING (APPEND-ONLY)
    # ================================================================
    
    def load_new_raw(self, source: str, last_ts: Optional[datetime] = None) -> pd.DataFrame:
        """
        Carrega novos dados raw (append-only)
        
        Args:
            source: 'pipelines' ou 'jobs'
            last_ts: Se None, usa watermark; se fornecido, usa esse timestamp
        
        Returns:
            DataFrame com novos registros
        """
        if last_ts is None:
            last_ts = self.get_watermark(source)
        
        # Se não há watermark, busca todos os dados disponíveis
        # (na prática, você carregaria do GitLab API aqui)
        # Por enquanto, vamos ler dos arquivos JSON existentes
        
        raw_dir = Config.DATA_RAW_DIR
        if source == 'pipelines':
            file_path = raw_dir / "pipelines.json"
            if not file_path.exists():
                return pd.DataFrame()
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            df = pd.DataFrame(data)
            if 'updated_at' in df.columns:
                df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True)
                if last_ts:
                    # Normaliza timezone: converte last_ts para UTC se necessário
                    if isinstance(last_ts, datetime):
                        if last_ts.tzinfo is None:
                            # Se last_ts é naive, assume UTC
                            last_ts = last_ts.replace(tzinfo=timezone.utc)
                        else:
                            # Se já tem timezone, converte para UTC
                            last_ts = last_ts.astimezone(timezone.utc)
                    df = df[df['updated_at'] > last_ts]
            
            self.stats['rows_read'] = len(df)
            return df
        
        elif source == 'jobs':
            # Carrega todos os jobs_*.json
            jobs_files = list(raw_dir.glob("jobs_*.json"))
            all_jobs = []
            
            for file_path in jobs_files:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    all_jobs.extend(data)
            
            if not all_jobs:
                return pd.DataFrame()
            
            df = pd.DataFrame(all_jobs)
            if 'created_at' in df.columns:
                df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
                if last_ts:
                    # Normaliza timezone: converte last_ts para UTC se necessário
                    if isinstance(last_ts, datetime):
                        if last_ts.tzinfo is None:
                            # Se last_ts é naive, assume UTC
                            last_ts = last_ts.replace(tzinfo=timezone.utc)
                        else:
                            # Se já tem timezone, converte para UTC
                            last_ts = last_ts.astimezone(timezone.utc)
                    df = df[df['created_at'] > last_ts]
            
            self.stats['rows_read'] = len(df)
            return df
        
        return pd.DataFrame()
    
    def append_raw_to_db(self, source: str, df: pd.DataFrame):
        """
        Insere dados raw no banco (append-only, ON CONFLICT DO NOTHING)
        
        Args:
            source: 'pipelines' ou 'jobs'
            df: DataFrame com dados
        """
        if df.empty:
            return
        
        # Limpa valores NaN/NaT antes de converter para JSON
        def clean_dict(d):
            """Remove NaN, NaT e inf do dicionário, converte Timestamp para string"""
            if isinstance(d, dict):
                return {k: clean_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [clean_dict(item) for item in d]
            elif pd.isna(d):
                return None
            elif isinstance(d, (float, int)) and (np.isinf(d) or np.isnan(d)):
                return None
            elif isinstance(d, (pd.Timestamp, datetime)):
                # Converte Timestamp/datetime para string ISO
                return d.isoformat() if hasattr(d, 'isoformat') else str(d)
            else:
                return d
        
        with self.conn.cursor() as cur:
            if source == 'pipelines':
                # Mapeia colunas
                for _, row in df.iterrows():
                    # Limpa o dicionário antes de converter para JSON
                    row_dict = row.to_dict()
                    row_dict_clean = clean_dict(row_dict)
                    
                    cur.execute(
                        """
                        INSERT INTO pipelines_raw (
                            id, project_id, status, ref, sha, web_url,
                            created_at, updated_at, finished_at, source_data
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            row.get('id'),
                            Config.PROJECT_ID,
                            row.get('status'),
                            row.get('ref'),
                            row.get('sha'),
                            row.get('web_url'),
                            pd.to_datetime(row.get('created_at')) if pd.notna(row.get('created_at')) else None,
                            pd.to_datetime(row.get('updated_at')) if pd.notna(row.get('updated_at')) else None,
                            pd.to_datetime(row.get('finished_at')) if pd.notna(row.get('finished_at')) else None,
                            Json(row_dict_clean)
                        )
                    )
            
            elif source == 'jobs':
                for _, row in df.iterrows():
                    pipeline_id = row.get('pipeline', {}).get('id') if isinstance(row.get('pipeline'), dict) else row.get('pipeline_id')
                    
                    # Limpa o dicionário antes de converter para JSON
                    row_dict = row.to_dict()
                    row_dict_clean = clean_dict(row_dict)
                    
                    cur.execute(
                        """
                        INSERT INTO jobs_raw (
                            id, pipeline_id, project_id, name, stage, status,
                            duration, queued_duration, failure_reason, retry_count,
                            web_url, created_at, started_at, finished_at, source_data
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            row.get('id'),
                            pipeline_id,
                            Config.PROJECT_ID,
                            row.get('name'),
                            row.get('stage'),
                            row.get('status'),
                            row.get('duration') if pd.notna(row.get('duration')) else None,
                            row.get('queued_duration') if pd.notna(row.get('queued_duration')) else None,
                            row.get('failure_reason'),
                            row.get('retry', 0) if pd.notna(row.get('retry', 0)) else 0,
                            row.get('web_url'),
                            pd.to_datetime(row.get('created_at')) if pd.notna(row.get('created_at')) else None,
                            pd.to_datetime(row.get('started_at')) if pd.notna(row.get('started_at')) else None,
                            pd.to_datetime(row.get('finished_at')) if pd.notna(row.get('finished_at')) else None,
                            Json(row_dict_clean)
                        )
                    )
            
            self.conn.commit()
            self.stats['rows_written'] += len(df)
    
    # ================================================================
    # METRICS COMPUTATION (UPSERT IDEMPOTENTE)
    # ================================================================
    
    def compute_metrics_daily(self, window_days: int = 3) -> int:
        """
        Calcula métricas diárias para janela deslizante
        
        Args:
            window_days: Dias para reprocessar (padrão 3 para corrigir atrasos). 
                        Use 0 para processar todos os dados disponíveis.
        
        Returns:
            Número de registros processados
        """
        # Se window_days é 0, processa tudo (sem limite de data)
        if window_days == 0:
            start_date = None
            end_date = datetime.now().date()
            print(f"📊 Calculando métricas diárias para TODOS os dados até {end_date}")
        else:
            # Determina janela: últimos N dias
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=window_days)
            print(f"📊 Calculando métricas diárias para janela: {start_date} a {end_date}")
        
        # Busca jobs raw da janela
        with self.conn.cursor() as cur:
            if start_date is None:
                # Processa tudo (sem filtro de data)
                cur.execute(
                    """
                    SELECT 
                        project_id,
                        name as job_name,
                        DATE(created_at) as day,
                        status,
                        duration,
                        failure_reason,
                        retry_count
                    FROM jobs_raw
                    WHERE project_id = %s
                      AND created_at <= %s + INTERVAL '1 day'
                    ORDER BY created_at
                    """,
                    (Config.PROJECT_ID, end_date)
                )
            else:
                # Processa apenas a janela especificada
                cur.execute(
                    """
                    SELECT 
                        project_id,
                        name as job_name,
                        DATE(created_at) as day,
                        status,
                        duration,
                        failure_reason,
                        retry_count
                    FROM jobs_raw
                    WHERE project_id = %s
                      AND created_at >= %s
                      AND created_at < %s + INTERVAL '1 day'
                    ORDER BY created_at
                    """,
                    (Config.PROJECT_ID, start_date, end_date)
                )
            
            rows = cur.fetchall()
            if not rows:
                print("   ℹ️  Nenhum dado na janela")
                return 0
            
            df = pd.DataFrame(rows, columns=[
                'project_id', 'job_name', 'day', 'status', 'duration', 'failure_reason', 'retry_count'
            ])
            
            # Converte duration para float (pode vir como Decimal do PostgreSQL)
            if 'duration' in df.columns:
                df['duration'] = pd.to_numeric(df['duration'], errors='coerce').astype('float64')
            
            # Converte retry_count para int
            if 'retry_count' in df.columns:
                df['retry_count'] = pd.to_numeric(df['retry_count'], errors='coerce').fillna(0).astype('int64')
        
        # Agrega por (project_id, job_name, day)
        metrics = df.groupby(['project_id', 'job_name', 'day']).agg({
            'status': [
                ('builds', lambda x: (x == 'success').sum() + (x == 'failed').sum()),
                ('fails', lambda x: (x == 'failed').sum())
            ],
            'duration': [
                ('p95_duration', lambda x: x.quantile(0.95) if len(x) > 0 else None),
                ('p99_duration', lambda x: x.quantile(0.99) if len(x) > 0 else None),
                ('avg_duration', 'mean'),
                ('total_duration', 'sum')
            ],
            'retry_count': 'max',
            'failure_reason': lambda x: json.dumps(x[x.notna()].value_counts().head(5).to_dict())
        }).reset_index()
        
        metrics.columns = ['project_id', 'job_name', 'day', 'builds', 'fails', 
                          'p95_duration', 'p99_duration', 'avg_duration', 'total_duration',
                          'max_retries', 'error_types']
        
        # UPSERT idempotente
        with self.conn.cursor() as cur:
            for _, row in metrics.iterrows():
                cur.execute(
                    """
                    INSERT INTO metrics_daily (
                        project_id, job_name, day, builds, fails,
                        p95_duration, p99_duration, avg_duration, total_duration,
                        max_retries, error_types
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (project_id, job_name, day) DO UPDATE
                    SET
                        builds = EXCLUDED.builds,
                        fails = EXCLUDED.fails,
                        p95_duration = EXCLUDED.p95_duration,
                        p99_duration = EXCLUDED.p99_duration,
                        avg_duration = EXCLUDED.avg_duration,
                        total_duration = EXCLUDED.total_duration,
                        max_retries = EXCLUDED.max_retries,
                        error_types = EXCLUDED.error_types,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        int(row['project_id']),
                        str(row['job_name']),
                        row['day'],
                        int(row['builds']),
                        int(row['fails']),
                        float(row['p95_duration']) if pd.notna(row['p95_duration']) else None,
                        float(row['p99_duration']) if pd.notna(row['p99_duration']) else None,
                        float(row['avg_duration']) if pd.notna(row['avg_duration']) else None,
                        float(row['total_duration']) if pd.notna(row['total_duration']) else None,
                        int(row['max_retries']) if pd.notna(row['max_retries']) else 0,
                        row['error_types']
                    )
                )
            
            self.conn.commit()
            count = len(metrics)
            self.stats['rows_processed'] += count
            print(f"   ✅ {count} métricas diárias atualizadas (UPSERT idempotente)")
            return count
    
    # ================================================================
    # FEATURE ENGINEERING
    # ================================================================
    
    def build_features(self, window_days: int = 30, feature_version: int = 1) -> int:
        """
        Constrói features para janela deslizante
        
        Args:
            window_days: Janela de dias (padrão 30). Use 0 para processar todos os dados.
            feature_version: Versão do schema de features
        
        Returns:
            Número de features geradas
        """
        end_date = datetime.now().date()
        
        # Se window_days é 0, processa tudo (sem limite de data)
        if window_days == 0:
            start_date = None
            print(f"🔧 Construindo features (v{feature_version}) para TODOS os dados até {end_date}")
        else:
            start_date = end_date - timedelta(days=window_days)
            print(f"🔧 Construindo features (v{feature_version}) para janela: {start_date} a {end_date}")
        
        # Busca métricas diárias agregadas
        with self.conn.cursor() as cur:
            if start_date is None:
                # Processa tudo (sem filtro de data)
                cur.execute(
                    """
                    SELECT 
                        project_id, job_name, day,
                        builds, fails, p95_duration, avg_duration, max_retries
                    FROM metrics_daily
                    WHERE project_id = %s
                      AND day <= %s
                    ORDER BY day
                    """,
                    (Config.PROJECT_ID, end_date)
                )
            else:
                # Processa apenas a janela especificada
                cur.execute(
                    """
                    SELECT 
                        project_id, job_name, day,
                        builds, fails, p95_duration, avg_duration, max_retries
                    FROM metrics_daily
                    WHERE project_id = %s
                      AND day >= %s
                      AND day <= %s
                    ORDER BY day
                    """,
                    (Config.PROJECT_ID, start_date, end_date)
                )
            
            rows = cur.fetchall()
            if not rows:
                print("   ℹ️  Nenhuma métrica na janela")
                return 0
            
            df = pd.DataFrame(rows, columns=[
                'project_id', 'job_name', 'day', 'builds', 'fails',
                'p95_duration', 'avg_duration', 'max_retries'
            ])
        
        # Agrega por job_name (últimos N dias)
        features = df.groupby(['project_id', 'job_name']).agg({
            'builds': 'sum',
            'fails': 'sum',
            'p95_duration': 'mean',
            'avg_duration': 'mean',
            'max_retries': 'max'
        }).reset_index()
        
        features['fail_rate'] = features['fails'] / (features['builds'] + 1)
        # Converte p95_duration para float antes de fillna para evitar warning
        features['dur_total'] = pd.to_numeric(features['p95_duration'], errors='coerce').fillna(0.0)
        
        # Constrói payload JSONB conforme feature_schema
        feature_list = []
        for _, row in features.iterrows():
            entity_key = f"{int(row['project_id'])}:{row['job_name']}"
            
            payload = {
                'dur_total': float(row['dur_total']) if pd.notna(row['dur_total']) else 0.0,
                'stage_build': float(row['avg_duration']) * 0.4 if pd.notna(row['avg_duration']) else 0.0,
                'stage_test': float(row['avg_duration']) * 0.5 if pd.notna(row['avg_duration']) else 0.0,
                'stage_deploy': float(row['avg_duration']) * 0.1 if pd.notna(row['avg_duration']) else 0.0,
                'fail_rate': float(row['fail_rate']),
                'max_retries': int(row['max_retries']) if pd.notna(row['max_retries']) else 0
            }
            
            event_time = datetime.combine(end_date, datetime.min.time())
            
            feature_list.append({
                'entity_key': entity_key,
                'feature_version': feature_version,
                'payload': payload,
                'event_time': event_time
            })
        
        # UPSERT em features_offline e features_online
        with self.conn.cursor() as cur:
            for feat in feature_list:
                # Offline (histórico)
                cur.execute(
                    """
                    INSERT INTO features_offline (entity_key, feature_version, payload, event_time)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (entity_key, feature_version) DO UPDATE
                    SET payload = EXCLUDED.payload, event_time = EXCLUDED.event_time
                    """,
                    (feat['entity_key'], feat['feature_version'], Json(feat['payload']), feat['event_time'])
                )
                
                # Online (cache atual)
                cur.execute(
                    """
                    INSERT INTO features_online (entity_key, feature_version, payload)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (entity_key) DO UPDATE
                    SET feature_version = EXCLUDED.feature_version,
                        payload = EXCLUDED.payload,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (feat['entity_key'], feat['feature_version'], Json(feat['payload']))
                )
            
            self.conn.commit()
            count = len(feature_list)
            self.stats['rows_processed'] += count
            print(f"   ✅ {count} features geradas e atualizadas (UPSERT idempotente)")
            return count
    
    # ================================================================
    # MAIN ETL PROCESS
    # ================================================================
    
    def run(self, reprocess_window_days: int = 3):
        """
        Executa ETL incremental completo
        
        Args:
            reprocess_window_days: Dias para reprocessar (janela deslizante)
        """
        import time
        start_time = time.time()
        
        print("🔄 Iniciando ETL Incremental...")
        print()
        
        # 1. Carrega novos dados raw
        print("📥 Carregando novos dados raw...")
        last_ts_pipelines = self.get_watermark('pipelines')
        df_pipelines = self.load_new_raw('pipelines', last_ts_pipelines)
        
        if not df_pipelines.empty:
            print(f"   ✅ {len(df_pipelines)} novos pipelines")
            self.append_raw_to_db('pipelines', df_pipelines)
            
            # Atualiza watermark
            if 'updated_at' in df_pipelines.columns:
                max_ts = df_pipelines['updated_at'].max()
                if pd.notna(max_ts):
                    self.update_watermark('pipelines', max_ts)
                    self.stats['last_ts'] = max_ts
        
        last_ts_jobs = self.get_watermark('jobs')
        df_jobs = self.load_new_raw('jobs', last_ts_jobs)
        
        if not df_jobs.empty:
            print(f"   ✅ {len(df_jobs)} novos jobs")
            self.append_raw_to_db('jobs', df_jobs)
            
            # Atualiza watermark
            if 'created_at' in df_jobs.columns:
                max_ts = df_jobs['created_at'].max()
                if pd.notna(max_ts):
                    self.update_watermark('jobs', max_ts)
        
        # 2. Calcula métricas diárias (janela deslizante)
        print()
        metrics_count = self.compute_metrics_daily(window_days=reprocess_window_days)
        if metrics_count > 0:
            self.stats['window_reprocessed'] = True
        
        # 3. Constrói features (usa a mesma janela que as métricas)
        print()
        feature_version = self._get_current_feature_version()
        # Se reprocess_window_days é 0, processa tudo. Caso contrário, usa 30 dias para features
        feature_window = 0 if reprocess_window_days == 0 else 30
        features_count = self.build_features(window_days=feature_window, feature_version=feature_version)
        
        # 4. Log de estatísticas
        self.stats['duration_sec'] = time.time() - start_time
        
        print()
        print("📊 RESUMO ETL:")
        print(f"   Linhas lidas: {self.stats['rows_read']}")
        print(f"   Linhas processadas: {self.stats['rows_processed']}")
        print(f"   Linhas gravadas: {self.stats['rows_written']}")
        print(f"   Janela reprocessada: {self.stats['window_reprocessed']}")
        print(f"   Último timestamp: {self.stats['last_ts']}")
        print(f"   Tempo total: {self.stats['duration_sec']:.2f}s")
        print()
        print("✅ ETL Incremental concluído!")
    
    def _get_current_feature_version(self) -> int:
        """Obtém versão atual de features"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT value FROM kv_config WHERE key = 'FEATURE_VERSION_CURRENT'")
            row = cur.fetchone()
            if row:
                return int(row[0])
            return 1

