#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard Builder - Relatório HTML com Design Patterns

Design Patterns Aplicados:
1. Builder Pattern: DashboardBuilder para construir HTML progressivamente
2. Strategy Pattern: Diferentes estratégias de análise (anomalias, erros)
3. Separation of Concerns: Cada classe tem uma responsabilidade única
4. Data Class: Modelos de dados estruturados
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')
import os, sys

# Garante import absoluto de src/* quando executado via Streamlit/subprocess
try:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
except Exception:
    pass

# Garante flushing imediato para feedback em UIs/CI
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# Importar requests apenas se necessário (para extração de logs)
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ================================================================
# CONFIGURAÇÕES (via Config para suportar múltiplos projetos)
# ================================================================
try:
    from src.core.config import Config
    Config.validate()
    RAW_DIR = Config.DATA_RAW_DIR
    PROC_DIR = Config.DATA_PROCESSED_DIR
    FIGURES_DIR = Config.FIGURES_DIR
except Exception:
    # Fallback (não recomendado): diretórios padrão
    RAW_DIR = Path("dados/raw")
    PROC_DIR = Path("dados/processed")
    FIGURES_DIR = PROC_DIR / "figuras"

OUTPUT_HTML = PROC_DIR / "RELATORIO_FINAL.html"

# ================================================================
# DATA CLASSES (Modelos de Dados)
# ================================================================

@dataclass
class Statistics:
    """Estatísticas gerais dos pipelines"""
    total: int
    success: int
    failed: int
    success_rate: float
    avg_duration: float
    median_duration: float

@dataclass
class Anomaly:
    """Anomalia detectada em um pipeline"""
    pipeline_id: int
    type: str
    problem: str
    details: str
    solution: str
    example: str
    critical: bool = False
    web_url: Optional[str] = None

@dataclass
class JobError:
    """Erro em um job específico"""
    pipeline_id: int
    job_name: str
    simple_error: str
    solutions: List[str]
    original_error: str
    web_url: Optional[str] = None
    job_url: Optional[str] = None

# ================================================================
# STATISTICS CALCULATOR (Calculador de Estatísticas)
# ================================================================

class StatisticsCalculator:
    """
    Responsabilidade: Calcular estatísticas dos pipelines
    Design Pattern: Separation of Concerns
    """
    
    def calculate(self, df: pd.DataFrame) -> Statistics:
        """Calcula estatísticas gerais"""
        total = len(df)
        success = len(df[df['status'] == 'success'])
        failed = len(df[df['status'] == 'failed'])
        success_rate = (success / total * 100) if total > 0 else 0
        
        # Detectar coluna de duração
        duration_col = self._find_duration_column(df)
        
        if duration_col:
            avg_duration = df[duration_col].mean()
            median_duration = df[duration_col].median()
        else:
            avg_duration = 0
            median_duration = 0
        
        return Statistics(
            total=total,
            success=success,
            failed=failed,
            success_rate=success_rate,
            avg_duration=avg_duration,
            median_duration=median_duration
        )
    
    def _find_duration_column(self, df: pd.DataFrame) -> Optional[str]:
        """Detecta qual coluna contém a duração"""
        for col in ['duration_sec', 'dur_total']:
            if col in df.columns:
                return col
        return None

# ================================================================
# ANOMALY DETECTOR (Detector de Anomalias)
# ================================================================

class AnomalyDetector:
    """
    Responsabilidade: Detectar anomalias simples nos pipelines
    Design Pattern: Strategy Pattern (diferentes estratégias de detecção)
    """
    
    def __init__(self, df: pd.DataFrame, stats: Statistics):
        self.df = df
        self.stats = stats
        self.duration_col = self._find_duration_column()
    
    def _find_duration_column(self) -> Optional[str]:
        """Detecta qual coluna contém a duração"""
        for col in ['duration_sec', 'dur_total']:
            if col in self.df.columns:
                return col
        return None
    
    def detect_slow_pipelines(self) -> List[Anomaly]:
        """Detecta pipelines muito lentos (> percentil 90)"""
        if not self.duration_col:
            return []
        
        anomalies = []
        p90 = self.df[self.duration_col].quantile(0.90)
        slow_pipelines = self.df[self.df[self.duration_col] > p90]
        
        for _, pipe in slow_pipelines.head(10).iterrows():
            anomalies.append(Anomaly(
                pipeline_id=pipe['pipeline_id'],
                type='🐌 MUITO LENTO',
                problem='Este pipeline está MUITO LENTO',
                details=f"Duração: {pipe[self.duration_col]:.0f}s (normal: {self.stats.median_duration:.0f}s)",
                solution='Paralelizar tarefas ou otimizar código',
                example='Se testes demoram muito: rode em paralelo (parallel: 5)',
                critical=False,
                web_url=pipe.get('web_url')
            ))
        
        return anomalies
    
    def detect_high_failure_rate(self) -> List[Anomaly]:
        """Detecta pipelines com alta taxa de falha"""
        if 'fail_rate' not in self.df.columns:
            return []
        
        anomalies = []
        high_failure = self.df[self.df['fail_rate'] > 0.2]
        
        for _, pipe in high_failure.head(10).iterrows():
            anomalies.append(Anomaly(
                pipeline_id=pipe['pipeline_id'],
                type='🔄 ALTA TAXA DE FALHA',
                problem='Este pipeline FALHA E TENTA DE NOVO várias vezes',
                details=f"Taxa de falha: {pipe['fail_rate']*100:.1f}%",
                solution='Encontrar o que está causando as falhas e corrigir',
                example='Se erro de rede: adicionar retry automático (retry: 2)',
                critical=True,
                web_url=pipe.get('web_url')
            ))
        
        return anomalies
    
    def detect_all(self) -> List[Anomaly]:
        """Detecta todas as anomalias"""
        anomalies = []
        anomalies.extend(self.detect_slow_pipelines())
        anomalies.extend(self.detect_high_failure_rate())
        return anomalies

# ================================================================
# ERROR ANALYZER (Analisador de Erros)
# ================================================================

class ErrorLogExtractor:
    """
    Responsabilidade: Extrair apenas o trecho com erro do log do job
    Design Pattern: Separation of Concerns
    """
    
    def __init__(self, gitlab_api: str, project_id: str, headers: dict):
        self.gitlab_api = gitlab_api
        self.project_id = project_id
        self.headers = headers
    
    def extract_error_snippet(self, job_id: int, max_lines: int = 50) -> Optional[str]:
        """
        Extrai apenas o trecho com erro do log do job
        
        Estratégia:
        1. Busca as últimas N linhas do log (onde geralmente está o erro)
        2. Procura por palavras-chave de erro (Error, FAILED, Exception, etc.)
        3. Retorna o trecho relevante
        """
        if not REQUESTS_AVAILABLE:
            return None
        
        try:
            # Busca o trace do job
            trace_url = f"{self.gitlab_api}/projects/{self.project_id}/jobs/{job_id}/trace"
            response = requests.get(trace_url, headers=self.headers, timeout=15)
            
            if response.status_code == 404:
                # Job não encontrado ou log não disponível
                return None
            elif response.status_code != 200:
                # Outro erro HTTP
                return None
            
            log_text = response.text
            
            # Se log vazio, retorna None
            if not log_text or len(log_text.strip()) == 0:
                return None
            
            # Divide em linhas
            lines = log_text.split('\n')
            
            # Se log muito pequeno, retorna tudo
            if len(lines) <= 10:
                return log_text[:2000]
            
            # Estratégia 1: Buscar seção com palavras-chave de erro
            error_keywords = ['ERROR', 'FAILED', 'Exception', 'Error:', 'FATAL', 'Traceback', 'FAIL', '✖', '❌', 'error', 'failed', 'exception']
            
            # Procura de trás para frente (erros geralmente estão no final)
            error_start_idx = None
            for i in range(len(lines) - 1, max(0, len(lines) - 200), -1):
                line_upper = lines[i].upper()
                if any(keyword.upper() in line_upper for keyword in error_keywords):
                    error_start_idx = max(0, i - 5)  # 5 linhas de contexto antes
                    break
            
            # Se encontrou erro, extrai trecho
            if error_start_idx is not None:
                error_snippet = '\n'.join(lines[error_start_idx:])
                # Limita tamanho
                if len(error_snippet) > 2000:
                    error_snippet = error_snippet[:2000] + "\n... (truncado)"
                return error_snippet
            
            # Estratégia 2: Se não encontrou palavras-chave, pega últimas linhas
            # Aumenta para 100 linhas para pegar mais contexto
            last_lines = lines[-min(max_lines * 2, 100):]
            snippet = '\n'.join(last_lines)
            
            # Remove linhas muito vazias no início
            snippet_lines = snippet.split('\n')
            while snippet_lines and not snippet_lines[0].strip():
                snippet_lines.pop(0)
            snippet = '\n'.join(snippet_lines)
            
            # Limita tamanho
            if len(snippet) > 2000:
                snippet = snippet[:2000] + "\n... (truncado)"
            
            # Se snippet muito pequeno ou vazio, retorna None (usa fallback)
            if len(snippet.strip()) < 50:
                return None
            
            return snippet
            
        except requests.exceptions.Timeout:
            # Timeout - retorna None para usar fallback
            return None
        except requests.exceptions.RequestException:
            # Erro de rede - retorna None para usar fallback
            return None
        except Exception as e:
            # Qualquer outro erro - retorna None para usar fallback
            return None


class ErrorAnalyzer:
    """
    Responsabilidade: Analisar erros em jobs e traduzir para linguagem simples
    Design Pattern: Separation of Concerns
    """
    
    def __init__(self, raw_dir: Path, log_extractor: Optional[ErrorLogExtractor] = None):
        self.raw_dir = raw_dir
        self.log_extractor = log_extractor
    
    def analyze_job_errors(self, pipelines_df: Optional[pd.DataFrame] = None) -> List[JobError]:
        """Analisa erros em jobs de todos os pipelines"""
        errors = []
        
        # Criar mapeamento pipeline_id -> web_url do DataFrame
        url_map = {}
        if pipelines_df is not None and 'web_url' in pipelines_df.columns:
            url_map = dict(zip(pipelines_df['pipeline_id'], pipelines_df['web_url']))
        
        for job_file in self.raw_dir.glob("jobs_*.json"):
            try:
                with open(job_file, 'r') as f:
                    jobs = json.load(f)
                
                for job in jobs:
                    if job.get('status') == 'failed':
                        pipeline_id = int(job_file.stem.split('_')[1])
                        error_msg = job.get('failure_reason', 'Desconhecido')
                        simple_error = self._translate_error(error_msg)
                        solutions = self._get_solutions(simple_error)
                        
                        # Buscar web_url: primeiro do mapeamento, depois do próprio job
                        web_url = url_map.get(pipeline_id)
                        if not web_url and 'pipeline' in job and isinstance(job['pipeline'], dict):
                            web_url = job['pipeline'].get('web_url')
                        
                        # URL do job específico (para ver logs completos)
                        job_url = job.get('web_url')
                        
                        # Extrair trecho de erro do log (se disponível)
                        error_snippet = None
                        if self.log_extractor and 'id' in job:
                            try:
                                job_id = job['id']
                                error_snippet = self.log_extractor.extract_error_snippet(job_id)
                                if error_snippet:
                                    print(f"   ✓ Log extraído para job {job_id} ({len(error_snippet)} chars)")
                            except Exception as e:
                                # Se falhar, continua sem trecho (silenciosamente)
                                pass
                        
                        # Usa snippet do log se disponível, senão usa failure_reason com mensagem
                        if error_snippet:
                            original_error = error_snippet
                        else:
                            # Se não conseguiu extrair, mostra mensagem informativa
                            original_error = f"failure_reason: {error_msg}\n\n(Log completo disponível no GitLab - clique no link acima)"
                        
                        errors.append(JobError(
                            pipeline_id=pipeline_id,
                            job_name=job.get('name', 'unknown'),
                            simple_error=simple_error,
                            solutions=solutions,
                            original_error=original_error,
                            web_url=web_url,
                            job_url=job_url
                        ))
            except:
                continue
        
        return errors
    
    def _translate_error(self, error_msg: str) -> str:
        """Traduz mensagens de erro técnicas para linguagem simples"""
        if not isinstance(error_msg, str):
            return "⚠️ ERRO DESCONHECIDO"
        
        msg = error_msg.lower()
        
        if 'timeout' in msg or 'timed out' in msg:
            return "⏱️ DEMOROU DEMAIS - Pipeline levou muito tempo e foi cancelado"
        
        if 'no module' in msg or 'cannot import' in msg or 'importerror' in msg:
            return "📦 FALTA BIBLIOTECA - Algum pacote não está instalado"
        
        if 'npm err' in msg or 'yarn error' in msg:
            return "📦 FALTA PACOTE NODE - Problema com npm/yarn install"
        
        if 'connection refused' in msg or 'network' in msg or 'failed to connect' in msg:
            return "🌐 SEM CONEXÃO - Não conseguiu conectar na internet/servidor"
        
        if 'permission denied' in msg or 'access denied' in msg or '403' in msg:
            return "🔒 SEM PERMISSÃO - Não tem autorização para acessar algo"
        
        if 'out of memory' in msg or 'oom' in msg:
            return "💾 SEM MEMÓRIA - Gastou toda a RAM disponível"
        
        if 'no space left' in msg or 'disk full' in msg:
            return "💿 DISCO CHEIO - Não tem mais espaço em disco"
        
        if 'test' in msg and 'fail' in msg:
            return "❌ TESTE FALHOU - Algum teste não passou"
        
        if 'syntax error' in msg or 'compilation' in msg:
            return "🔧 ERRO DE CÓDIGO - Problema de sintaxe ou compilação"
        
        if 'docker' in msg:
            return "🐳 ERRO DOCKER - Problema com imagem ou container"
        
        if 'rate limit' in msg or '429' in msg:
            return "🚦 MUITAS REQUISIÇÕES - API bloqueou por excesso de uso"
        
        if 'database' in msg or 'sql' in msg:
            return "🗄️ ERRO DE BANCO - Problema ao conectar/usar banco de dados"
        
        return "⚠️ ERRO DESCONHECIDO - Veja os logs para mais detalhes"
    
    def _get_solutions(self, simple_error: str) -> List[str]:
        """Retorna soluções práticas baseadas no erro"""
        solutions_map = {
            "⏱️ DEMOROU DEMAIS": [
                "Aumentar timeout no .gitlab-ci.yml: 'timeout: 2h'",
                "Paralelizar testes lentos",
                "Usar cache para não reinstalar tudo sempre"
            ],
            "📦 FALTA BIBLIOTECA": [
                "Adicionar no requirements.txt: 'nome-do-pacote==versão'",
                "Rodar 'pip install -r requirements.txt' no CI",
                "Verificar se está usando Python correto"
            ],
            "📦 FALTA PACOTE NODE": [
                "Adicionar no package.json: 'npm install nome --save'",
                "Fazer commit do package-lock.json",
                "Limpar cache: 'npm cache clean --force'"
            ],
            "🌐 SEM CONEXÃO": [
                "Adicionar retry: 'retry: 2' no .gitlab-ci.yml",
                "Verificar se URL está correta",
                "Testar conexão localmente primeiro"
            ],
            "🔒 SEM PERMISSÃO": [
                "Verificar token em Settings > CI/CD > Variables",
                "Token precisa ter permissão 'read_api'",
                "Verificar se projeto é público ou se você tem acesso"
            ],
            "💾 SEM MEMÓRIA": [
                "Aumentar RAM do runner: Settings > CI/CD > Runners",
                "Otimizar código (procurar memory leaks)",
                "Reduzir paralelização de testes"
            ],
            "💿 DISCO CHEIO": [
                "Limpar cache no after_script: 'rm -rf node_modules/'",
                "Reduzir tamanho de artefatos",
                "Aumentar disco do runner"
            ],
            "❌ TESTE FALHOU": [
                "Rodar teste localmente: 'pytest test_file.py -v'",
                "Verificar se teste não é 'flaky' (falha aleatória)",
                "Atualizar teste ou corrigir código"
            ],
            "🔧 ERRO DE CÓDIGO": [
                "Rodar linter localmente: 'flake8 .' ou 'eslint .'",
                "Corrigir erro de sintaxe apontado",
                "Usar pre-commit hooks para evitar"
            ],
            "🐳 ERRO DOCKER": [
                "Verificar se imagem existe: 'docker pull <imagem>'",
                "Testar Dockerfile localmente",
                "Verificar credenciais do registry"
            ],
            "🚦 MUITAS REQUISIÇÕES": [
                "Adicionar delay: 'time.sleep(1)' entre requests",
                "Usar token com limite maior",
                "Aguardar alguns minutos antes de tentar novamente"
            ],
            "🗄️ ERRO DE BANCO": [
                "Executar migrations: 'python manage.py migrate'",
                "Verificar connection string",
                "Confirmar se DB está rodando no before_script"
            ]
        }
        
        for key, solutions in solutions_map.items():
            if key in simple_error:
                return solutions
        
        return [
            "Ver logs completos do job",
            "Tentar reproduzir erro localmente",
            "Comparar com pipelines que funcionaram"
        ]

# ================================================================
# DASHBOARD BUILDER (Construtor do Dashboard)
# ================================================================

class DashboardBuilder:
    """
    Responsabilidade: Construir o HTML do dashboard progressivamente
    Design Pattern: Builder Pattern
    """
    
    def __init__(self):
        self.html_parts = []
        self.stats = None
        self.anomalies = []
        self.errors = []
        self.df_pipes = None  # DataFrame para insights
        self.job_insights = None  # Insights de jobs agregados
    
    def set_statistics(self, stats: Statistics) -> 'DashboardBuilder':
        """Define as estatísticas gerais"""
        self.stats = stats
        return self
    
    def set_dataframe(self, df: pd.DataFrame) -> 'DashboardBuilder':
        """Define o DataFrame para gerar insights"""
        self.df_pipes = df
        return self
    
    def set_job_insights(self, insights: Dict[str, str]) -> 'DashboardBuilder':
        """Define insights textuais calculados a partir dos jobs brutos"""
        self.job_insights = insights
        return self
    
    def add_anomalies(self, anomalies: List[Anomaly]) -> 'DashboardBuilder':
        """Adiciona anomalias detectadas"""
        self.anomalies = anomalies
        return self
    
    def add_errors(self, errors: List[JobError]) -> 'DashboardBuilder':
        """Adiciona erros de jobs"""
        self.errors = errors
        return self
    
    def build(self) -> str:
        """Constrói o HTML completo"""
        html = self._build_header()
        html += self._build_statistics_section()
        html += self._build_alert_section()
        html += self._build_insights_section()  # Nova seção de insights
        html += self._build_anomalies_section()
        html += self._build_errors_section()
        html += self._build_summary_section()
        html += self._build_footer()
        html += self._build_closing_tags()
        
        return html
    
    def _build_header(self) -> str:
        """Constrói o cabeçalho do HTML"""
        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Relatório de Pipelines CI/CD</title>
    {self._get_css()}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Relatório de Pipelines CI/CD</h1>
            <p>Análise Completa com Estatísticas e Visualizações</p>
            <p style="font-size: 0.9em; margin-top: 10px;">Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}</p>
        </div>
        <div class="content">
"""
    
    def _build_statistics_section(self) -> str:
        """Constrói a seção de estatísticas"""
        if not self.stats:
            return ""
        
        return f"""
            <!-- Estatísticas Gerais -->
            <div class="stats">
                <div class="stat-card">
                    <div class="number">{self.stats.total}</div>
                    <div class="label">Total de Pipelines</div>
                </div>
                <div class="stat-card success">
                    <div class="number">{self.stats.success}</div>
                    <div class="label">✅ Com Sucesso</div>
                </div>
                <div class="stat-card danger">
                    <div class="number">{self.stats.failed}</div>
                    <div class="label">❌ Com Falha</div>
                </div>
                <div class="stat-card {'success' if self.stats.success_rate >= 80 else 'warning' if self.stats.success_rate >= 60 else 'danger'}">
                    <div class="number">{self.stats.success_rate:.1f}%</div>
                    <div class="label">Taxa de Sucesso</div>
                </div>
            </div>
"""
    
    def _build_alert_section(self) -> str:
        """Constrói alertas importantes"""
        if not self.stats or self.stats.success_rate >= 60:
            return ""
        
        return """
            <div class="alert">
                <strong>⚠️ ATENÇÃO: Taxa de sucesso baixa!</strong>
                Menos de 60% dos seus pipelines estão funcionando corretamente. 
                Isso indica problemas sérios que precisam de atenção imediata.
            </div>
"""
    
    def _build_insights_section(self) -> str:
        """Constrói a seção de insights detalhados"""
        if self.df_pipes is None or len(self.df_pipes) == 0:
            return ""
        
        df = self.df_pipes
        insights = []
        
        # 1. Top performers (pipelines rápidos e bem-sucedidos)
        duration_col = 'dur_total' if 'dur_total' in df.columns else None
        if duration_col:
            successful = df[df['status'] == 'success'].copy()
            if len(successful) > 0:
                fastest = successful.nsmallest(5, duration_col)
                insights.append({
                    'title': '🚀 Top Pipelines (Mais Rápidos e Bem-Sucedidos)',
                    'content': self._format_top_pipelines(fastest, duration_col)
                })
        
        # 2. Análise por estágio
        stage_cols = [c for c in df.columns if c.startswith('stage_')]
        if stage_cols:
            stage_analysis = []
            for col in stage_cols[:3]:  # build, test, deploy
                if col in df.columns:
                    stage_name = col.replace('stage_', '').title()
                    avg = df[col].mean()
                    median = df[col].median()
                    p95 = df[col].quantile(0.95)
                    stage_analysis.append(f"<strong>{stage_name}:</strong> média {avg:.1f}s, mediana {median:.1f}s, p95 {p95:.1f}s")
            
            if stage_analysis:
                insights.append({
                    'title': '📊 Análise por Estágio',
                    'content': '<br>'.join(stage_analysis)
                })
        
        # 3. Estatísticas de duração
        if duration_col:
            p50 = df[duration_col].quantile(0.50)
            p75 = df[duration_col].quantile(0.75)
            p90 = df[duration_col].quantile(0.90)
            p95 = df[duration_col].quantile(0.95)
            insights.append({
                'title': '⏱️ Distribuição de Tempo',
                'content': f"""
                    <p><strong>Mediana (p50):</strong> {p50:.1f}s ({p50/60:.1f} min)</p>
                    <p><strong>p75:</strong> {p75:.1f}s ({p75/60:.1f} min)</p>
                    <p><strong>p90:</strong> {p90:.1f}s ({p90/60:.1f} min)</p>
                    <p><strong>p95:</strong> {p95:.1f}s ({p95/60:.1f} min)</p>
                    <p style="margin-top: 10px; color: #666;">
                        💡 <strong>Insight:</strong> 50% dos pipelines terminam em menos de {p50/60:.1f} minutos, 
                        mas 5% levam mais de {p95/60:.1f} minutos. 
                        {'Otimize os pipelines lentos para melhorar a média geral.' if p95 > p50 * 2 else 'Suas pipelines têm tempos consistentes!'}
                    </p>
                """
            })
        
        # 4. Análise de retries
        if 'max_retries' in df.columns:
            total_retries = df['max_retries'].sum()
            pipelines_with_retries = len(df[df['max_retries'] > 0])
            if total_retries > 0:
                insights.append({
                    'title': '🔄 Análise de Retries',
                    'content': f"""
                        <p><strong>Total de retries:</strong> {total_retries:.0f}</p>
                        <p><strong>Pipelines com retries:</strong> {pipelines_with_retries} ({pipelines_with_retries/len(df)*100:.1f}%)</p>
                        <p style="margin-top: 10px; color: #666;">
                            💡 <strong>Insight:</strong> {'Muitos pipelines estão falhando e tentando novamente. Considere investigar as causas raiz.' if pipelines_with_retries > len(df) * 0.1 else 'Poucos pipelines precisam de retry - boa estabilidade!'}
                        </p>
                    """
                })
        
        # 5. Taxa de sucesso por padrão
        if 'fail_rate' in df.columns:
            stable = len(df[df['fail_rate'] == 0])
            unstable = len(df[df['fail_rate'] > 0.5])
            insights.append({
                'title': '📈 Estabilidade dos Pipelines',
                'content': f"""
                    <p><strong>Pipelines estáveis (0% falha):</strong> {stable} ({stable/len(df)*100:.1f}%)</p>
                    <p><strong>Pipelines instáveis (>50% falha):</strong> {unstable} ({unstable/len(df)*100:.1f}%)</p>
                    <p style="margin-top: 10px; color: #666;">
                        💡 <strong>Insight:</strong> {'Foque em corrigir os pipelines instáveis primeiro.' if unstable > 0 else 'Excelente! Todos os pipelines estão estáveis.'}
                    </p>
                """
            })
        
        if not insights:
            return ""
        
        html = """
            <div class="section">
                <h2 class="section-title">💡 Insights e Análises Detalhadas</h2>
                <p style="margin-bottom: 20px;">Análises inteligentes para entender melhor o desempenho dos seus pipelines:</p>
                <div class="insights-grid">
"""
        
        for insight in insights:
            html += f"""
                    <div class="insight-card">
                        <h3>{insight['title']}</h3>
                        <div class="insight-content">
                            {insight['content']}
                        </div>
                    </div>
"""
        
        # Bloco adicional com insights de jobs (se existirem)
        if self.job_insights:
            html += f"""
                    <div class=\"insight-card\">
                        <h3>🧰 Insights de Jobs (agregados)</h3>
                        <div class=\"insight-content\">
                            {self.job_insights.get('top_failing_jobs', '')}
                            {self.job_insights.get('common_failure_reasons', '')}
                            {self.job_insights.get('queue_pressure', '')}
                            {self.job_insights.get('flaky_jobs', '')}
                        </div>
                    </div>
            """
        
        html += """
                </div>
            </div>
"""
        
        return html
    
    def _format_top_pipelines(self, df: pd.DataFrame, duration_col: str) -> str:
        """Formata lista de top pipelines"""
        html_parts = []
        for _, row in df.iterrows():
            pipeline_id = row.get('pipeline_id', 'N/A')
            duration = row[duration_col]
            web_url = row.get('web_url', '')
            link = f'<a href="{web_url}" target="_blank" class="pipeline-link">Pipeline #{pipeline_id} 🔗</a>' if web_url else f'Pipeline #{pipeline_id}'
            html_parts.append(f"<p>{link}: {duration:.1f}s ({duration/60:.1f} min)</p>")
        return ''.join(html_parts)
    
    def _build_anomalies_section(self) -> str:
        """Constrói a seção de anomalias"""
        if not self.anomalies:
            return """
            <div class="section">
                <div class="no-issues">
                    <div class="emoji">🎉</div>
                    <strong>Nenhuma anomalia detectada!</strong><br>
                    Seus pipelines estão rodando dentro do esperado.
                </div>
            </div>
"""
        
        html = f"""
            <div class="section">
                <h2 class="section-title">⚠️ Problemas Detectados ({len(self.anomalies)})</h2>
                <p style="margin-bottom: 20px;">Encontramos estes pipelines com comportamento incomum:</p>
"""
        
        for anom in self.anomalies[:10]:
            # Criar link clicável se web_url disponível
            pipeline_link = f'<a href="{anom.web_url}" target="_blank" class="pipeline-link">Pipeline #{anom.pipeline_id} 🔗</a>' if anom.web_url else f'<span class="pipeline-id">Pipeline #{anom.pipeline_id}</span>'
            
            html += f"""
                <div class="anomaly-card {'critical' if anom.critical else ''}">
                    {pipeline_link}
                    <h3>{anom.type}</h3>
                    <div class="problema">{anom.problem}</div>
                    <div class="detalhes">{anom.details}</div>
                    <div class="solution">
                        <h4>💡 Como Resolver:</h4>
                        {anom.solution}
                        <div class="exemplo">
                            <strong>Exemplo prático:</strong><br>
                            {anom.example}
                        </div>
                    </div>
                </div>
"""
        
        html += """
            </div>
"""
        return html
    
    def _build_errors_section(self) -> str:
        """Constrói a seção de erros"""
        if not self.errors:
            return ""
        
        html = f"""
            <div class="section">
                <h2 class="section-title">❌ Erros em Jobs ({len(self.errors)})</h2>
                <p style="margin-bottom: 20px;">Jobs que falharam e como corrigir:</p>
"""
        
        for error in self.errors[:15]:
            # Criar link clicável se web_url disponível
            pipeline_link = f'<a href="{error.web_url}" target="_blank" class="pipeline-link">Pipeline #{error.pipeline_id} 🔗</a>' if error.web_url else f'<span class="pipeline-id">Pipeline #{error.pipeline_id}</span>'
            
            html += f"""
                <div class="error-card">
                    {pipeline_link}
                    <span class="job-name">{error.job_name}</span>
                    <div class="error-simple">{error.simple_error}</div>
                    <div class="solution">
                        <h4>💡 Como Resolver:</h4>
                        <ol class="solutions-list">
"""
            
            for sol in error.solutions:
                html += f"                            <li>{sol}</li>\n"
            
            # Link para ver logs completos no GitLab
            log_link = f'<a href="{error.job_url}" target="_blank" style="color: #667eea; text-decoration: none; font-weight: bold;">📋 Ver log completo no GitLab →</a>' if error.job_url else 'Logs não disponíveis'
            
            html += f"""
                        </ol>
                    </div>
                    <div style="margin-top: 15px; padding: 15px; background: #e8f4f8; border-radius: 5px; border-left: 3px solid #17a2b8;">
                        <strong style="color: #0c5460;">💡 Dica:</strong> Para investigar o erro completo, veja o log detalhado no GitLab:<br>
                        <div style="margin-top: 8px;">
                            {log_link}
                        </div>
                    </div>
                    <details style="margin-top: 15px;">
                        <summary style="cursor: pointer; color: #666;">Ver trecho de erro do log</summary>
                        <div style="background: #f8f9fa; padding: 10px; margin-top: 10px; border-radius: 5px; font-size: 0.85em; font-family: monospace; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">
{error.original_error}
                        </div>
                        <div style="margin-top: 10px; padding: 8px; background: #fff3cd; border-radius: 5px; font-size: 0.85em;">
                            <em style="color: #856404;">
                                💡 Este é o trecho do log onde o erro ocorreu. Para ver o log completo, clique no link acima.
                            </em>
                        </div>
                    </details>
                </div>
"""
        
        html += """
            </div>
"""
        return html
    
    def _build_summary_section(self) -> str:
        """Constrói o resumo geral"""
        if not self.stats:
            return ""
        
        return f"""
            <div class="section">
                <h2 class="section-title">📈 Resumo Geral</h2>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
                    <p><strong>Duração média:</strong> {self.stats.avg_duration:.0f} segundos ({self.stats.avg_duration/60:.1f} minutos)</p>
                    <p><strong>Duração mediana:</strong> {self.stats.median_duration:.0f} segundos ({self.stats.median_duration/60:.1f} minutos)</p>
                    <p><strong>Pipelines analisados:</strong> {self.stats.total}</p>
                    <p><strong>Problemas encontrados:</strong> {len(self.anomalies)} anomalias + {len(self.errors)} erros</p>
                </div>
            </div>
"""
    
    def _build_footer(self) -> str:
        """Constrói o rodapé"""
        return """
        </div>
        <div class="footer">
            <p><strong>Próximos Passos:</strong></p>
            <p>1. Resolver erros críticos primeiro (marcados em vermelho)</p>
            <p>2. Otimizar pipelines lentos</p>
            <p>3. Monitorar taxa de sucesso</p>
            <p>4. Analisar os gráficos acima para identificar padrões</p>
            <p style="margin-top: 20px; opacity: 0.7;">
                Relatório gerado automaticamente pelo sistema de análise de CI/CD<br>
                <small>Design Patterns: Builder, Strategy, Separation of Concerns</small>
            </p>
        </div>
    </div>
"""
    
    def _build_closing_tags(self) -> str:
        """Fecha as tags HTML"""
        return """
</body>
</html>
"""
    
    def _get_css(self) -> str:
        """Retorna o CSS completo"""
        return """
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .content {
            padding: 40px;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        
        .stat-card {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            border: 2px solid #e9ecef;
        }
        
        .stat-card .number {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }
        
        .stat-card .label {
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .stat-card.success .number { color: #28a745; }
        .stat-card.warning .number { color: #ffc107; }
        .stat-card.danger .number { color: #dc3545; }
        
        .section {
            margin-bottom: 40px;
        }
        
        .section-title {
            font-size: 1.8em;
            margin-bottom: 20px;
            color: #2d3748;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        
        .anomaly-card {
            background: #fff3cd;
            border-left: 5px solid #ffc107;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
        }
        
        .anomaly-card.critical {
            background: #f8d7da;
            border-left-color: #dc3545;
        }
        
        .anomaly-card h3 {
            color: #856404;
            margin-bottom: 10px;
            font-size: 1.3em;
        }
        
        .anomaly-card.critical h3 {
            color: #721c24;
        }
        
        .anomaly-card .pipeline-id {
            display: inline-block;
            background: rgba(0,0,0,0.1);
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        .pipeline-link {
            display: inline-block;
            background: rgba(102, 126, 234, 0.2);
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #667eea;
            text-decoration: none;
            transition: all 0.3s ease;
        }
        
        .pipeline-link:hover {
            background: rgba(102, 126, 234, 0.3);
            transform: translateY(-2px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        
        .anomaly-card .problema {
            font-size: 1.1em;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .anomaly-card .detalhes {
            color: #666;
            margin: 10px 0;
        }
        
        .solution {
            background: #d4edda;
            border-left: 5px solid #28a745;
            padding: 15px;
            margin-top: 15px;
            border-radius: 5px;
        }
        
        .solution h4 {
            color: #155724;
            margin-bottom: 10px;
        }
        
        .solution .exemplo {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            margin-top: 10px;
        }
        
        .error-card {
            background: #f8d7da;
            border-left: 5px solid #dc3545;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
        }
        
        .error-card h3 {
            color: #721c24;
            margin-bottom: 10px;
        }
        
        .error-card .job-name {
            background: rgba(0,0,0,0.1);
            padding: 5px 10px;
            border-radius: 5px;
            display: inline-block;
            margin-bottom: 10px;
        }
        
        .error-simple {
            font-size: 1.2em;
            font-weight: bold;
            margin: 10px 0;
            color: #721c24;
        }
        
        .solutions-list {
            margin-top: 15px;
        }
        
        .solutions-list li {
            margin: 8px 0;
            padding-left: 10px;
        }
        
        .alert {
            background: #d1ecf1;
            border: 2px solid #bee5eb;
            color: #0c5460;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .alert strong {
            display: block;
            font-size: 1.2em;
            margin-bottom: 10px;
        }
        
        .footer {
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }
        
        .no-issues {
            text-align: center;
            padding: 40px;
            background: #d4edda;
            border-radius: 15px;
            color: #155724;
            font-size: 1.2em;
        }
        
        .no-issues .emoji {
            font-size: 3em;
            margin-bottom: 20px;
        }
        
        .insights-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .insight-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 25px;
            border-radius: 15px;
            border: 2px solid #e9ecef;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .insight-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }
        
        .insight-card h3 {
            color: #2d3748;
            margin-bottom: 15px;
            font-size: 1.3em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .insight-content {
            color: #4a5568;
            line-height: 1.8;
        }
        
        .insight-content p {
            margin: 8px 0;
        }
        
        .insight-content strong {
            color: #2d3748;
        }
    </style>
"""

# ================================================================
# MAIN FUNCTION (Função Principal)
# ================================================================

def generate_dashboard():
    """
    Função principal que coordena a geração do dashboard
    Design Pattern: Facade Pattern (simplifica interface complexa)
    """
    print("📊 Gerando Relatório Final Completo...")
    print()
    
    # 1. Carregar dados
    try:
        df_pipes = pd.read_csv(PROC_DIR / "pipelines.csv")
    except FileNotFoundError:
        print("❌ Erro: Execute 'make normalize' primeiro!")
        return
    
    # 2. Calcular estatísticas
    stats_calc = StatisticsCalculator()
    stats = stats_calc.calculate(df_pipes)
    
    # 3. Detectar anomalias
    anomaly_detector = AnomalyDetector(df_pipes, stats)
    anomalies = anomaly_detector.detect_all()
    
    # 4. Preparar extrator de logs (se disponível)
    log_extractor = None
    try:
        from src.core.config import Config
        if Config.PROJECT_ID and Config.TOKEN:
            log_extractor = ErrorLogExtractor(
                gitlab_api=Config.GITLAB_API,
                project_id=Config.PROJECT_ID,
                headers=Config.get_headers()
            )
            print("📋 Extração de trechos de erro do log: habilitada")
            print(f"   API: {Config.GITLAB_API}")
            print(f"   Projeto: {Config.PROJECT_ID}")
        else:
            print("⚠️  Extração de logs desabilitada: PROJECT_ID ou TOKEN não configurados")
    except Exception as e:
        # Se não conseguir configurar, continua sem extração de logs
        print(f"⚠️  Extração de logs desabilitada: {e}")
    
    # 5. Analisar erros
    print("\n🔍 Analisando erros em jobs...")
    error_analyzer = ErrorAnalyzer(RAW_DIR, log_extractor=log_extractor)
    errors = error_analyzer.analyze_job_errors(df_pipes)
    print(f"   ✅ {len(errors)} erros encontrados")
    
    # 6. Calcular insights agregados de jobs (erros comuns, fila, flakiness)
    job_insights = {}
    try:
        from collections import Counter, defaultdict
        fail_by_job = Counter()
        reason_counter = Counter()
        queue_durations = []
        outcomes_by_job: Dict[str, Counter] = defaultdict(Counter)
        for job_file in RAW_DIR.glob("jobs_*.json"):
            with open(job_file, 'r') as f:
                jobs = json.load(f)
            for job in jobs:
                name = str(job.get('name', 'unknown'))
                status = str(job.get('status', ''))
                if status == 'failed':
                    fail_by_job[name] += 1
                    reason = str(job.get('failure_reason', 'desconhecido'))
                    reason_counter[reason] += 1
                if 'queued_duration' in job and isinstance(job['queued_duration'], (int, float)):
                    queue_durations.append(float(job['queued_duration']))
                outcomes_by_job[name][status] += 1
        # Top que mais falham
        if fail_by_job:
            top = fail_by_job.most_common(5)
            items = ''.join([f"<li><strong>{n}</strong>: {c} falhas</li>" for n,c in top])
            job_insights['top_failing_jobs'] = f"<p><strong>Top jobs que mais falham:</strong></p><ul>{items}</ul>"
        # Motivos mais comuns
        if reason_counter:
            top_r = reason_counter.most_common(5)
            items = ''.join([f"<li>{r}: {c}</li>" for r,c in top_r])
            job_insights['common_failure_reasons'] = f"<p><strong>Motivos de falha mais comuns:</strong></p><ul>{items}</ul>"
        # Pressão de fila
        if queue_durations:
            avg_q = sum(queue_durations)/len(queue_durations)
            job_insights['queue_pressure'] = f"<p><strong>Tempo médio em fila:</strong> {avg_q:.1f}s</p>"
        # Flakiness
        flaky_list = []
        for name, counts in outcomes_by_job.items():
            if counts.get('success', 0) > 0 and counts.get('failed', 0) > 0:
                flaky_list.append((name, counts['failed'], counts['success']))
        if flaky_list:
            flaky_list.sort(key=lambda x: (x[1]+x[2]), reverse=True)
            top_flaky = flaky_list[:5]
            rows = ''.join([f"<li><strong>{n}</strong>: {f} falhas / {s} sucessos</li>" for n,f,s in top_flaky])
            job_insights['flaky_jobs'] = f"<p><strong>Jobs instáveis (flaky):</strong></p><ul>{rows}</ul>"
    except Exception:
        pass

    # 7. Construir HTML
    builder = DashboardBuilder()
    html = (builder
            .set_statistics(stats)
            .set_dataframe(df_pipes)  # Passa DataFrame para insights
            .set_job_insights(job_insights)
            .add_anomalies(anomalies)
            .add_errors(errors)
            .build())
    
    # 8. Salvar arquivo
    OUTPUT_HTML.write_text(html, encoding='utf-8')
    
    # 9. Exibir resumo
    print("=" * 64)
    print("✅ RELATÓRIO GERADO COM SUCESSO!")
    print("=" * 64)
    print()
    print(f"📄 Arquivo: {OUTPUT_HTML}")
    print()
    print("📊 RESUMO RÁPIDO:")
    print(f"   • Total de pipelines: {stats.total}")
    print(f"   • Taxa de sucesso: {stats.success_rate:.1f}%")
    print(f"   • Anomalias encontradas: {len(anomalies)}")
    print(f"   • Erros em jobs: {len(errors)}")
    print()

# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    generate_dashboard()
    
    # Evita tentar abrir navegador em ambiente de container/CI/Streamlit
    SKIP_OPEN = os.environ.get("DASHBOARD_NO_OPEN") == "1" or Path("/.dockerenv").exists() or os.environ.get("CI") == "true"
    if not SKIP_OPEN:
        import platform
        import subprocess
        html_path = str(OUTPUT_HTML.absolute())
        sistema = platform.system()
        try:
            if sistema == "Darwin":  # Mac
                subprocess.run(["open", html_path], check=False)
            elif sistema == "Linux":
                subprocess.run(["xdg-open", html_path], check=False)
            elif sistema == "Windows":
                subprocess.run(["start", html_path], shell=True, check=False)
            print("🌐 Dashboard aberto no navegador!")
        except Exception:
            print(f"💡 Abra manualmente: {html_path}")
