"""
Configurações Centralizadas

Pattern: Singleton para configurações globais
"""

import os
from pathlib import Path


class Config:
    """Configurações globais do sistema"""
    
    # GitLab API
    GITLAB_API = os.getenv("GITLAB_API", "http://localhost:8080/api/v4")
    PROJECT_ID = os.getenv("PROJECT_ID")
    TOKEN = os.getenv("TOKEN")
    MAX_PIPELINES = os.getenv("MAX_PIPELINES", None)
    
    # Diretórios
    BASE_DIR = Path(__file__).parent.parent.parent
    # Diretórios segregados por projeto
    _PROJECT_FOLDER = PROJECT_ID if PROJECT_ID else "default"
    DATA_RAW_DIR = BASE_DIR / "dados" / "raw" / _PROJECT_FOLDER
    DATA_PROCESSED_DIR = BASE_DIR / "dados" / "processed" / _PROJECT_FOLDER
    # Armazena figuras dentro de dados/processed/<PROJECT_ID>/figuras
    FIGURES_DIR = DATA_PROCESSED_DIR / "figuras"
    
    # Machine Learning
    ML_CONTAMINATION = 0.1  # Proporção esperada de anomalias
    ML_RANDOM_STATE = 42
    ML_N_CLUSTERS = 3  # Número de clusters para K-Means
    
    # Thresholds
    THRESHOLD_P95 = 95  # Percentil para alertas
    THRESHOLD_P99 = 99
    
    @classmethod
    def validate(cls):
        """Valida configurações obrigatórias"""
        if not cls.PROJECT_ID:
            raise ValueError("PROJECT_ID não configurado. Use: export PROJECT_ID=...")
        
        # Cria diretórios se não existirem
        cls.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        cls.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_headers(cls):
        """Retorna headers para requisições GitLab"""
        return {"PRIVATE-TOKEN": cls.TOKEN} if cls.TOKEN else {}

