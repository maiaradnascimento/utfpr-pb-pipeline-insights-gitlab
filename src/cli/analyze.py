"""
Script de análise com métricas detalhadas
Objetivos específicos:
- Análise estatística detalhada (p50, p75, p90, p95, p99)
- Identificação de outliers
"""
import os, pandas as pd, numpy as np
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.core.config import Config

Config.validate()

FIG_DIR = Config.FIGURES_DIR
PROC_DIR = Config.DATA_PROCESSED_DIR

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(PROC_DIR, exist_ok=True)

df = pd.read_csv(PROC_DIR / "pipelines.csv")

print(f"📊 Analisando {len(df)} pipelines...")

# ====== 1. ESTATÍSTICAS DESCRITIVAS AVANÇADAS ======
def pctl(s, p):
    s = s.dropna()
    return float(np.percentile(s, p)) if len(s) > 0 else 0.0

metrics = ["stage_build", "stage_test", "stage_deploy", "dur_total", "fail_rate", "max_retries"]
stats_data = []

for metric in metrics:
    if metric in df.columns:
        serie = df[metric].dropna()
        if len(serie) > 0:
            stats_data.append({
                "metrica": metric,
                "media": serie.mean(),
                "mediana": serie.median(),
                "desvio_padrao": serie.std(),
                "p50": pctl(serie, 50),
                "p75": pctl(serie, 75),
                "p90": pctl(serie, 90),
                "p95": pctl(serie, 95),
                "p99": pctl(serie, 99),
                "min": serie.min(),
                "max": serie.max(),
                "count": len(serie)
            })

stats_df = pd.DataFrame(stats_data)
stats_df.to_csv(PROC_DIR / "stats_detalhadas.csv", index=False)
print("✅ Estatísticas detalhadas salvas em stats_detalhadas.csv")

# ====== 2. IDENTIFICAÇÃO DE OUTLIERS ======
outliers_data = []
for col in ["stage_build", "stage_test", "stage_deploy", "dur_total"]:
    if col in df.columns:
        serie = df[col].dropna()
        if len(serie) > 0:
            Q1 = serie.quantile(0.25)
            Q3 = serie.quantile(0.75)
            IQR = Q3 - Q1
            limite_inferior = Q1 - 1.5 * IQR
            limite_superior = Q3 + 1.5 * IQR
            
            outliers = df[(df[col] < limite_inferior) | (df[col] > limite_superior)]
            
            if len(outliers) > 0:
                for _, row in outliers.iterrows():
                    outliers_data.append({
                        "pipeline_id": row["pipeline_id"],
                        "metrica": col,
                        "valor": row[col],
                        "limite_inferior": limite_inferior,
                        "limite_superior": limite_superior,
                        "tipo": "abaixo" if row[col] < limite_inferior else "acima"
                    })

if outliers_data:
    outliers_df = pd.DataFrame(outliers_data)
    outliers_df.to_csv(PROC_DIR / "outliers_identificados.csv", index=False)
    print(f"✅ {len(outliers_data)} outliers identificados e salvos")

# ====== 4. RESUMO CONSOLIDADO ======
resumo = {
    "total_pipelines": len(df),
    "pipelines_sucesso": len(df[df["status"] == "success"]) if "status" in df.columns else 0,
    "pipelines_falha": len(df[df["status"] == "failed"]) if "status" in df.columns else 0,
    "taxa_sucesso": len(df[df["status"] == "success"]) / len(df) * 100 if "status" in df.columns and len(df) > 0 else 0,
    "duracao_media_total": df["dur_total"].mean() if "dur_total" in df.columns else 0,
    "duracao_mediana_total": df["dur_total"].median() if "dur_total" in df.columns else 0,
    "duracao_p95_total": pctl(df.get("dur_total", pd.Series([])), 95),
    "retries_medio": df["max_retries"].mean() if "max_retries" in df.columns else 0,
    "data_analise": datetime.now().isoformat()
}

pd.DataFrame([resumo]).to_csv(PROC_DIR / "resumo_analise.csv", index=False)
print("✅ Resumo consolidado salvo")

print("\n" + "="*60)
print("📊 ANÁLISE CONCLUÍDA COM SUCESSO!")
print("="*60)
print(f"Pipelines analisados: {resumo['total_pipelines']}")
print(f"Taxa de sucesso: {resumo['taxa_sucesso']:.1f}%")
print(f"Duração mediana: {resumo['duracao_mediana_total']:.1f}s")
print(f"Duração p95: {resumo['duracao_p95_total']:.1f}s")
print("\nArquivos gerados:")
print(f"  📄 {PROC_DIR}/stats_detalhadas.csv")
print(f"  📄 {PROC_DIR}/resumo_analise.csv")
print(f"  📄 {PROC_DIR}/outliers_identificados.csv")
print("="*60)

