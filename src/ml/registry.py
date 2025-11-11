"""
Model Registry - Versionamento de Modelos e Transformadores

Gerencia versionamento de modelos, transformadores e feature schemas.
"""

import os
import json
import pickle
from pathlib import Path
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extras import Json

from src.core.config import Config


class ModelRegistry:
    """Registry para versionamento de modelos ML"""
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'pipeline_optimizer')}"
        )
        self.models_dir = Config.BASE_DIR / "models"
        self.models_dir.mkdir(exist_ok=True)
        self.transformers_dir = self.models_dir / "transformers"
        self.transformers_dir.mkdir(exist_ok=True)
        self.schemas_dir = self.models_dir / "schemas"
        self.schemas_dir.mkdir(exist_ok=True)
    
    def _get_conn(self):
        """Abre conexão com banco"""
        return psycopg2.connect(self.db_url)
    
    def current_model_version(self) -> int:
        """
        Retorna versão atual do modelo em produção
        
        Returns:
            Versão do modelo (int)
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM kv_config WHERE key = 'MODEL_CURRENT'")
                row = cur.fetchone()
                if row:
                    return int(row[0])
                return 1
    
    def bump_model_version(self) -> int:
        """
        Incrementa versão do modelo
        
        Returns:
            Nova versão
        """
        current = self.current_model_version()
        new_version = current + 1
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kv_config SET value = %s WHERE key = 'MODEL_CURRENT'",
                    (str(new_version),)
                )
                conn.commit()
        
        return new_version
    
    def save_model(self, model: Any, version: int, model_type: str = "isolation_forest"):
        """
        Salva modelo versionado
        
        Args:
            model: Objeto do modelo (sklearn, xgboost, etc)
            version: Versão do modelo
            model_type: Tipo do modelo (ex: 'isolation_forest', 'xgboost')
        """
        model_path = self.models_dir / f"model_v{version}.pkl"
        
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        print(f"💾 Modelo salvo: {model_path}")
    
    def load_model(self, version: Optional[int] = None) -> Any:
        """
        Carrega modelo versionado
        
        Args:
            version: Versão do modelo (None = versão atual)
        
        Returns:
            Objeto do modelo
        """
        if version is None:
            version = self.current_model_version()
        
        model_path = self.models_dir / f"model_v{version}.pkl"
        
        if not model_path.exists():
            raise FileNotFoundError(f"Modelo v{version} não encontrado: {model_path}")
        
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        return model
    
    def save_transformer(self, transformer: Any, version: int, name: str = "scaler"):
        """
        Salva transformador versionado (scaler, encoder, etc)
        
        Args:
            transformer: Objeto transformador
            version: Versão do transformador
            name: Nome do transformador (ex: 'scaler', 'encoder')
        """
        transformer_path = self.transformers_dir / f"{name}_v{version}.pkl"
        
        with open(transformer_path, 'wb') as f:
            pickle.dump(transformer, f)
        
        print(f"💾 Transformador salvo: {transformer_path}")
    
    def load_transformer(self, version: Optional[int] = None, name: str = "scaler") -> Any:
        """
        Carrega transformador versionado
        
        Args:
            version: Versão (None = versão atual)
            name: Nome do transformador
        
        Returns:
            Objeto transformador
        """
        if version is None:
            version = self.current_model_version()
        
        transformer_path = self.transformers_dir / f"{name}_v{version}.pkl"
        
        if not transformer_path.exists():
            raise FileNotFoundError(f"Transformador {name}_v{version} não encontrado: {transformer_path}")
        
        with open(transformer_path, 'rb') as f:
            transformer = pickle.load(f)
        
        return transformer
    
    def save_feature_schema(self, schema: Dict[str, Any], version: int):
        """
        Salva schema de features versionado
        
        Args:
            schema: Dicionário com ordem, dtype e transform de cada feature
            version: Versão do schema
        """
        schema_path = self.schemas_dir / f"feature_schema_v{version}.json"
        
        with open(schema_path, 'w') as f:
            json.dump(schema, f, indent=2)
        
        print(f"💾 Feature schema salvo: {schema_path}")
    
    def load_feature_schema(self, version: Optional[int] = None) -> Dict[str, Any]:
        """
        Carrega schema de features versionado
        
        Args:
            version: Versão (None = versão atual)
        
        Returns:
            Dicionário com schema
        """
        if version is None:
            version = self.current_model_version()
        
        schema_path = self.schemas_dir / f"feature_schema_v{version}.json"
        
        if not schema_path.exists():
            raise FileNotFoundError(f"Feature schema v{version} não encontrado: {schema_path}")
        
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        return schema
    
    def register_model(self, version: int, feature_version: int, model_type: str,
                      training_window_start: str, training_window_end: str,
                      metrics: Dict[str, Any], trained_by: str = "system"):
        """
        Registra modelo no banco de dados
        
        Args:
            version: Versão do modelo
            feature_version: Versão das features usadas
            model_type: Tipo do modelo
            training_window_start: Data início do treino (YYYY-MM-DD)
            training_window_end: Data fim do treino (YYYY-MM-DD)
            metrics: Métricas do modelo (dict)
            trained_by: Quem treinou (default: 'system')
        """
        model_path = f"models/model_v{version}.pkl"
        transformer_path = f"models/transformers/scaler_v{version}.pkl"
        schema_path = f"models/schemas/feature_schema_v{version}.json"
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Marca versão anterior como não atual
                cur.execute(
                    "UPDATE model_registry SET is_current = FALSE WHERE is_current = TRUE"
                )
                
                # Insere novo registro
                cur.execute(
                    """
                    INSERT INTO model_registry (
                        model_version, feature_version, model_type,
                        model_path, transformer_path, feature_schema_path,
                        training_window_start, training_window_end,
                        metrics, is_current, trained_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, TRUE, %s)
                    ON CONFLICT (model_version) DO UPDATE
                    SET feature_version = EXCLUDED.feature_version,
                        model_type = EXCLUDED.model_type,
                        model_path = EXCLUDED.model_path,
                        transformer_path = EXCLUDED.transformer_path,
                        feature_schema_path = EXCLUDED.feature_schema_path,
                        training_window_start = EXCLUDED.training_window_start,
                        training_window_end = EXCLUDED.training_window_end,
                        metrics = EXCLUDED.metrics,
                        is_current = EXCLUDED.is_current,
                        trained_by = EXCLUDED.trained_by
                    """,
                    (
                        version, feature_version, model_type,
                        model_path, transformer_path, schema_path,
                        training_window_start, training_window_end,
                        Json(metrics), trained_by
                    )
                )
                
                conn.commit()
        
        print(f"✅ Modelo v{version} registrado no banco")

