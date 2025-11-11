"""CLI - Interface de Linha de Comando"""

# Módulos CLI disponíveis:
# - fetch: Coleta dados do GitLab
# - normalize: Normaliza dados coletados
# - analyze: Análise estatística
# - recommend: Gera recomendações (usa strategies)
# - validate: Experimento controlado

__all__ = ['fetch', 'normalize', 'analyze', 'recommend', 'validate']
