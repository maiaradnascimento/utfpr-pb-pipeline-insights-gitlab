import os, glob, pandas as pd
import sys
from pathlib import Path

# Importa Config para usar diretórios por projeto
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.core.config import Config

Config.validate()
RAW_DIR = Config.DATA_RAW_DIR
PROC_DIR = Config.DATA_PROCESSED_DIR

os.makedirs(PROC_DIR, exist_ok=True)

if os.path.exists(RAW_DIR / "pipelines.json"):
    pipes = pd.read_json(RAW_DIR / "pipelines.json")
    ts_col = None
    for c in ["updated_at","created_at","finished_at"]:
        if c in pipes.columns: ts_col = c; break
    pipes = pipes.rename(columns={"id":"pipeline_id"})
    
    # Incluir web_url se disponível
    keep_cols = ["pipeline_id", "status"]
    if "web_url" in pipes.columns:
        keep_cols.append("web_url")
    if ts_col:
        keep_cols.append(ts_col)
        pipes = pipes[keep_cols].rename(columns={ts_col:"timestamp"})
    else:
        pipes = pipes[keep_cols]
        pipes["timestamp"] = pd.NaT

    jobs_frames=[]
    for fp in glob.glob(str(RAW_DIR / "jobs_*.json")):
        j = pd.read_json(fp)
        if not j.empty:
            # Extrai pipeline_id (pode vir como dict com 'id' ou como valor direto)
            if "pipeline" in j.columns:
                if isinstance(j["pipeline"].iloc[0], dict):
                    j["pipeline_id"] = j["pipeline"].apply(lambda x: x.get("id") if isinstance(x, dict) else x)
                else:
                    j["pipeline_id"] = j["pipeline"]
            
            # Seleciona e renomeia colunas
            keep = [c for c in ["pipeline_id","id","stage","duration","status","retry","failure_reason","name"] if c in j.columns]
            jj = j[keep].copy()
            
            # Renomeia colunas
            rename_map = {"id":"job_id","duration":"duration_sec","retry":"retries","failure_reason":"error_text","name":"job_name"}
            jj = jj.rename(columns=rename_map)
            
            # Garante que duration_sec é numérico
            if "duration_sec" in jj.columns:
                jj["duration_sec"] = pd.to_numeric(jj["duration_sec"], errors="coerce").fillna(0)
            
            # Garante que retries é numérico
            if "retries" in jj.columns:
                jj["retries"] = pd.to_numeric(jj["retries"], errors="coerce").fillna(0)
            
            # Garante que stage é string simples
            if "stage" in jj.columns:
                jj["stage"] = jj["stage"].astype(str)
            
            jobs_frames.append(jj)
    
    jobs = pd.concat(jobs_frames, ignore_index=True) if jobs_frames else pd.DataFrame(columns=["pipeline_id","job_id","stage","duration_sec","status","retries","error_text","job_name"])
else:
    pipes = pd.read_csv(RAW_DIR / "pipelines_sintetico.csv")
    jobs  = pd.read_csv(RAW_DIR / "jobs_sintetico.csv")

# agregações
try:
    # Garante que os campos necessários existem e são do tipo correto
    if "pipeline_id" not in jobs.columns:
        jobs["pipeline_id"] = 0
    if "stage" not in jobs.columns:
        jobs["stage"] = "unknown"
    if "duration_sec" not in jobs.columns:
        jobs["duration_sec"] = 0
    if "retries" not in jobs.columns:
        jobs["retries"] = 0
    if "error_text" not in jobs.columns:
        jobs["error_text"] = ""
    
    # Limpa valores NaN e garante tipos corretos
    jobs["pipeline_id"] = pd.to_numeric(jobs["pipeline_id"], errors="coerce").fillna(0).astype(int)
    jobs["stage"] = jobs["stage"].fillna("unknown").astype(str)
    jobs["duration_sec"] = pd.to_numeric(jobs["duration_sec"], errors="coerce").fillna(0)
    jobs["retries"] = pd.to_numeric(jobs["retries"], errors="coerce").fillna(0)
    
    dur = jobs.pivot_table(index="pipeline_id", columns="stage", values="duration_sec", aggfunc="sum").fillna(0)
    dur.columns = [f"stage_{c}" for c in dur.columns]
except Exception as e:
    print(f"Aviso: Erro ao criar pivot_table de duração: {e}")
    dur = pd.DataFrame()

try:
    fails = (jobs.assign(fail=lambda d: (d["status"]!="success").astype(int))
                 .groupby("pipeline_id")["fail"].mean().rename("fail_rate"))
except Exception as e:
    print(f"Aviso: Erro ao calcular fail_rate: {e}")
    fails = pd.Series(name="fail_rate", dtype=float)

try:
    retry = jobs.groupby("pipeline_id")["retries"].max().rename("max_retries")
except Exception as e:
    print(f"Aviso: Erro ao calcular retries: {e}")
    retry = pd.Series(name="max_retries", dtype=float)

try:
    errtxt = jobs.groupby("pipeline_id")["error_text"].apply(
        lambda s: " | ".join([str(e) for e in s.fillna("") if e and str(e) != "nan"])[:500]
    ).rename("error_text")
except Exception as e:
    print(f"Aviso: Erro ao processar error_text: {e}")
    errtxt = pd.Series(name="error_text", dtype=str)

# Merge das agregações
base = pipes.copy()

if not dur.empty:
    base = base.merge(dur.reset_index(), on="pipeline_id", how="left")

if not fails.empty:
    base = base.merge(fails.reset_index(), on="pipeline_id", how="left")

if not retry.empty:
    base = base.merge(retry.reset_index(), on="pipeline_id", how="left")

if not errtxt.empty:
    base = base.merge(errtxt.reset_index(), on="pipeline_id", how="left")

# Preenche valores faltantes
for c in ["fail_rate","max_retries","stage_build","stage_test","stage_deploy"]:
    if c in base.columns:
        base[c] = base[c].fillna(0)

# Calcula duração total
stage_cols = [c for c in base.columns if c.startswith("stage_")]
if stage_cols:
    base["dur_total"] = base[stage_cols].sum(axis=1)
else:
    base["dur_total"] = 0

out_fp = PROC_DIR / "pipelines.csv"
base.to_csv(out_fp, index=False)
print(f"OK: {out_fp}")
