"""
Modelos de Dados

Pattern: Data Classes para representar entidades do domínio
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class Job:
    """Representa um job de um pipeline"""
    job_id: int
    pipeline_id: int
    name: str
    stage: str
    duration_sec: float
    status: str
    retries: int = 0
    error_text: Optional[str] = None
    
    @property
    def is_failed(self) -> bool:
        """Verifica se o job falhou"""
        return self.status in ['failed', 'canceled']
    
    @property
    def is_slow(self) -> bool:
        """Verifica se o job é lento (heurística simples)"""
        return self.duration_sec > 300  # > 5 minutos


@dataclass
class Pipeline:
    """Representa um pipeline CI/CD"""
    pipeline_id: int
    status: str
    timestamp: Optional[datetime] = None
    jobs: List[Job] = field(default_factory=list)
    
    # Métricas agregadas
    dur_total: float = 0.0
    stage_build: float = 0.0
    stage_test: float = 0.0
    stage_deploy: float = 0.0
    fail_rate: float = 0.0
    max_retries: int = 0
    
    # Análise
    anomalia_score: Optional[float] = None
    is_anomaly: bool = False
    
    @property
    def is_successful(self) -> bool:
        """Verifica se o pipeline foi bem-sucedido"""
        return self.status == 'success'
    
    @property
    def total_jobs(self) -> int:
        """Retorna número total de jobs"""
        return len(self.jobs)
    
    @property
    def failed_jobs(self) -> int:
        """Retorna número de jobs que falharam"""
        return sum(1 for job in self.jobs if job.is_failed)
    
    def calculate_metrics(self):
        """Calcula métricas agregadas do pipeline"""
        if not self.jobs:
            return
        
        # Duração total
        self.dur_total = sum(job.duration_sec for job in self.jobs)
        
        # Duração por estágio
        stages = {'build': 0.0, 'test': 0.0, 'deploy': 0.0}
        for job in self.jobs:
            stage_clean = job.stage.lower().replace('.', '_').replace('-', '_')
            if 'build' in stage_clean or 'pre' in stage_clean:
                stages['build'] += job.duration_sec
            elif 'test' in stage_clean:
                stages['test'] += job.duration_sec
            elif 'deploy' in stage_clean or 'release' in stage_clean:
                stages['deploy'] += job.duration_sec
        
        self.stage_build = stages['build']
        self.stage_test = stages['test']
        self.stage_deploy = stages['deploy']
        
        # Taxa de falha
        if self.total_jobs > 0:
            self.fail_rate = self.failed_jobs / self.total_jobs
        
        # Retries máximos
        self.max_retries = max((job.retries for job in self.jobs), default=0)


@dataclass
class Recommendation:
    """Representa uma recomendação de otimização"""
    pipeline_id: int
    category: str
    action: str
    reason: str
    estimated_gain_sec: float
    estimated_gain_pct: float
    confidence: str  # ALTA, MÉDIA, BAIXA
    evidence: Dict[str, Any] = field(default_factory=dict)
    yaml_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            'pipeline_id': self.pipeline_id,
            'category': self.category,
            'action': self.action,
            'reason': self.reason,
            'estimated_gain_sec': self.estimated_gain_sec,
            'estimated_gain_pct': self.estimated_gain_pct,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'yaml_code': self.yaml_code
        }

