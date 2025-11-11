"""Strategies - Strategy Pattern para Recomendações"""

from .base import RecommendationStrategy
from .intelligent_strategy import IntelligentStrategy

__all__ = [
    'RecommendationStrategy',
    'IntelligentStrategy'
]

