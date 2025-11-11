"""
Intelligent Strategy - IA Inteligente com Clustering

Pattern: Strategy - Implementação mais sofisticada
"""

from typing import List
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from .base import RecommendationStrategy
from ..core.models import Recommendation
from ..core.config import Config


class IntelligentStrategy(RecommendationStrategy):
    """
    Estratégia inteligente que aprende dos dados
    
    - Isolation Forest para anomalias
    - K-Means para clustering
    - Thresholds adaptativos (p50-p99)
    - Análise contextual (múltiplas features)
    """
    
    def __init__(self):
        super().__init__("Intelligent-AI")
        self.anomaly_detector = IsolationForest(
            contamination=Config.ML_CONTAMINATION,
            random_state=Config.ML_RANDOM_STATE
        )
        self.clustering_model = KMeans(
            n_clusters=Config.ML_N_CLUSTERS,
            random_state=Config.ML_RANDOM_STATE
        )
    
    def recommend(self, df: pd.DataFrame) -> List[Recommendation]:
        """
        Gera recomendações inteligentes
        
        1. Clustering para agrupar pipelines similares
        2. Isolation Forest para detectar anomalias
        3. Análise contextual multi-feature
        4. Identificação de padrões
        """
        recommendations = []
        
        # Features
        feat_cols = ['dur_total', 'stage_build', 'stage_test', 'stage_deploy', 'fail_rate']
        feat_cols = [c for c in feat_cols if c in df.columns]
        
        if len(feat_cols) == 0 or len(df) < 10:
            return []
        
        # Prepara dados
        X = df[feat_cols].fillna(0).values
        
        # 1. Clustering
        clusters = self.clustering_model.fit_predict(X)
        df_analysis = df.copy()
        df_analysis['cluster'] = clusters
        
        # 2. Anomaly Detection
        predictions = self.anomaly_detector.fit_predict(X)
        scores = self.anomaly_detector.score_samples(X)
        df_analysis['anomalia_score'] = scores
        df_analysis['is_anomaly'] = predictions == -1
        
        # 3. Aprende thresholds por feature
        thresholds = self._learn_thresholds(df_analysis, feat_cols)
        
        # 4. Analisa anomalias
        anomalies = df_analysis[df_analysis['is_anomaly']]
        
        for _, pipeline in anomalies.iterrows():
            # Análise contextual completa
            context = self._analyze_context(pipeline, thresholds, feat_cols)
            
            if not context:
                continue
            
            # Identifica padrão
            pattern = self._identify_pattern(context)
            
            # Gera recomendação baseada no padrão
            rec = self._generate_recommendation_from_pattern(
                pipeline_id=pipeline['pipeline_id'],
                pattern=pattern,
                context=context,
                cluster=pipeline['cluster']
            )
            
            if rec:
                recommendations.append(rec)
        
        return recommendations
    
    def _learn_thresholds(self, df: pd.DataFrame, features: List[str]) -> dict:
        """Aprende thresholds dos dados (não hardcoded)"""
        thresholds = {}
        for feat in features:
            if feat in df.columns:
                thresholds[feat] = {
                    'p50': df[feat].quantile(0.50),
                    'p75': df[feat].quantile(0.75),
                    'p90': df[feat].quantile(0.90),
                    'p95': df[feat].quantile(0.95),
                    'p99': df[feat].quantile(0.99),
                    'mean': df[feat].mean(),
                    'std': df[feat].std()
                }
        return thresholds
    
    def _analyze_context(self, pipeline: pd.Series, thresholds: dict, features: List[str]) -> dict:
        """Analisa contexto completo (múltiplas features)"""
        context = {}
        
        for feat in features:
            if feat not in pipeline or feat not in thresholds:
                continue
            
            value = pipeline[feat]
            t = thresholds[feat]
            
            # Classifica nível
            if value > t['p99']:
                level = 'EXTREMO'
            elif value > t['p95']:
                level = 'MUITO_ALTO'
            elif value > t['p90']:
                level = 'ALTO'
            elif value > t['p75']:
                level = 'MEDIO_ALTO'
            else:
                level = 'NORMAL'
            
            # Calcula z-score
            z_score = 0
            if t['std'] > 0:
                z_score = (value - t['mean']) / t['std']
            
            context[feat] = {
                'value': value,
                'level': level,
                'z_score': z_score,
                'p50': t['p50'],
                'p95': t['p95']
            }
        
        return context
    
    def _identify_pattern(self, context: dict) -> dict:
        """Identifica padrões contextuais"""
        # Padrão 1: Build lento + fail_rate baixo → dependências
        if (context.get('stage_build', {}).get('level') in ['ALTO', 'MUITO_ALTO', 'EXTREMO'] and
            context.get('fail_rate', {}).get('level') in ['NORMAL', 'MEDIO_ALTO']):
            return {
                'name': 'slow_build_stable',
                'description': 'Build lento mas estável',
                'likely_cause': 'dependências',
                'action': 'cache',
                'category': 'Build'
            }
        
        # Padrão 2: Build lento + fail_rate alto → recursos
        if (context.get('stage_build', {}).get('level') in ['ALTO', 'MUITO_ALTO', 'EXTREMO'] and
            context.get('fail_rate', {}).get('level') in ['ALTO', 'MUITO_ALTO', 'EXTREMO']):
            return {
                'name': 'slow_build_unstable',
                'description': 'Build lento e instável',
                'likely_cause': 'recursos insuficientes',
                'action': 'resources',
                'category': 'Infraestrutura'
            }
        
        # Padrão 3: Test lento → paralelização
        if context.get('stage_test', {}).get('level') in ['ALTO', 'MUITO_ALTO', 'EXTREMO']:
            return {
                'name': 'slow_tests',
                'description': 'Testes lentos',
                'likely_cause': 'execução sequencial',
                'action': 'parallel',
                'category': 'Test'
            }
        
        # Padrão 4: Alta falha → flakiness
        if context.get('fail_rate', {}).get('level') in ['ALTO', 'MUITO_ALTO', 'EXTREMO']:
            return {
                'name': 'high_failure',
                'description': 'Alta taxa de falha',
                'likely_cause': 'flakiness',
                'action': 'retry',
                'category': 'Confiabilidade'
            }
        
        # Padrão genérico
        return {
            'name': 'generic',
            'description': 'Anomalia detectada',
            'likely_cause': 'desconhecida',
            'action': 'review',
            'category': 'Geral'
        }
    
    def _generate_recommendation_from_pattern(self, pipeline_id: int, pattern: dict, 
                                             context: dict, cluster: int) -> Recommendation:
        """Gera recomendação baseada no padrão identificado"""
        
        # Determina feature principal
        main_feature = max(
            context.items(),
            key=lambda x: abs(x[1].get('z_score', 0))
        )
        feat_name = main_feature[0]
        feat_info = main_feature[1]
        
        # Calcula ganho real
        gain = feat_info['value'] - feat_info['p50'] if feat_info['value'] > feat_info['p50'] else 0
        gain_pct = (gain / feat_info['value'] * 100) if feat_info['value'] > 0 else 0
        
        # Confiança baseada em z-score
        z = abs(feat_info['z_score'])
        confidence = 'ALTA' if z > 2.5 else 'MÉDIA' if z > 2.0 else 'BAIXA'
        
        # YAML específico
        yaml_code = self._generate_yaml(pattern['action'], {
            'path': 'node_modules/',
            'workers': 3
        })
        
        return Recommendation(
            pipeline_id=pipeline_id,
            category=pattern['category'],
            action=f"{pattern['action'].upper()}: {pattern['description']}",
            reason=f"Padrão '{pattern['name']}' identificado. Causa provável: {pattern['likely_cause']}",
            estimated_gain_sec=gain,
            estimated_gain_pct=gain_pct,
            confidence=confidence,
            evidence={
                'pattern': pattern['name'],
                'main_feature': feat_name,
                'z_score': feat_info['z_score'],
                'level': feat_info['level'],
                'cluster': cluster,
                'context': {k: v['level'] for k, v in context.items()}
            },
            yaml_code=yaml_code
        )

