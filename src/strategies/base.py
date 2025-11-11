"""
Base Strategy - Interface para Estratégias de Recomendação

Pattern: Strategy - Define interface comum para diferentes algoritmos
"""

from abc import ABC, abstractmethod
from typing import List
import pandas as pd
from ..core.models import Recommendation


class RecommendationStrategy(ABC):
    """
    Interface base para estratégias de recomendação
    
    Implementações concretas devem definir o método recommend()
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def recommend(self, df: pd.DataFrame) -> List[Recommendation]:
        """
        Gera recomendações baseadas nos dados
        
        Args:
            df: DataFrame com dados de pipelines processados
            
        Returns:
            Lista de objetos Recommendation
        """
        pass
    
    def _calculate_statistics(self, df: pd.DataFrame) -> dict:
        """
        Calcula estatísticas descritivas (reutilizável)
        
        Args:
            df: DataFrame com dados
            
        Returns:
            Dicionário com estatísticas por métrica
        """
        stats = {}
        
        metrics = ['dur_total', 'stage_build', 'stage_test', 'stage_deploy']
        
        for metric in metrics:
            if metric in df.columns:
                stats[metric] = {
                    'p50': df[metric].quantile(0.50),
                    'p75': df[metric].quantile(0.75),
                    'p90': df[metric].quantile(0.90),
                    'p95': df[metric].quantile(0.95),
                    'p99': df[metric].quantile(0.99),
                    'mean': df[metric].mean(),
                    'std': df[metric].std(),
                    'max': df[metric].max(),
                    'min': df[metric].min()
                }
        
        return stats
    
    def _generate_yaml(self, action_type: str, details: dict) -> str:
        """
        Gera código YAML GitLab CI para a recomendação
        
        Args:
            action_type: Tipo de ação (cache, parallel, retry, etc)
            details: Detalhes específicos da recomendação
            
        Returns:
            String com código YAML formatado
        """
        if action_type == 'cache':
            return f"""# Adicione ao seu job:
cache:
  key: ${{CI_COMMIT_REF_SLUG}}
  paths:
    - {details.get('path', 'node_modules/')}"""
        
        elif action_type == 'parallel':
            n = details.get('workers', 3)
            return f"""# Paralelização:
test:
  parallel: {n}
  script:
    - pytest --shard=${{CI_NODE_INDEX}}/${{CI_NODE_TOTAL}}"""
        
        elif action_type == 'retry':
            return """# Adicione retry:
.retry_template: &retry
  retry:
    max: 2
    when:
      - runner_system_failure
      - stuck_or_timeout_failure"""
        
        else:
            return "# Revise configuração do pipeline"
    
    def __str__(self) -> str:
        return f"RecommendationStrategy({self.name})"
    
    def __repr__(self) -> str:
        return self.__str__()

