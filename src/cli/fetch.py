"""
CLI - Fetch Data from GitLab

Coleta dados de pipelines via API do GitLab.
"""

import os
import json
import time
import requests
import pathlib
import sys
import argparse
from datetime import datetime, timezone

# Adiciona diretório raiz ao path para imports absolutos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.core.config import Config


def _load_last_sync(path: pathlib.Path):
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_last_sync(path: pathlib.Path, payload: dict):
    try:
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def fetch_pipelines(updated_after: str | None = None, incremental: bool = False):
    """Coleta pipelines do GitLab via API"""
    
    # Validar configurações
    try:
        Config.validate()
    except ValueError as e:
        print(f"❌ Erro: {e}")
        return False
    
    # Headers
    headers = Config.get_headers()
    
    # Limites
    max_pipelines = int(Config.MAX_PIPELINES) if Config.MAX_PIPELINES else None
    
    print("🔄 Iniciando coleta de dados do GitLab...")
    print(f"   API: {Config.GITLAB_API}")
    print(f"   Projeto: {Config.PROJECT_ID}")
    if max_pipelines:
        print(f"   Limite: {max_pipelines} pipelines")
    else:
        print(f"   Modo: TODOS os pipelines (paginação automática)")
    print()
    
    # Coleta pipelines
    print("📊 Coletando lista de pipelines...")
    last_sync_file = Config.DATA_RAW_DIR / ".last_sync.json"
    params_base = {}

    # Modo incremental: usa updated_after do arquivo de sync, se não houver, usa passado por arg/env
    if incremental:
        last = _load_last_sync(last_sync_file)
        if last and last.get("updated_after"):
            params_base["updated_after"] = last["updated_after"]
            print(f"   Incremental: updated_after={params_base['updated_after']}")
        elif updated_after:
            params_base["updated_after"] = updated_after
            print(f"   Incremental (manual): updated_after={updated_after}")
    elif updated_after:
        params_base["updated_after"] = updated_after
        print(f"   Filtro manual: updated_after={updated_after}")
    pipes = []
    page = 1
    per_page = 100
    
    while True:
        print(f"   Página {page}...", end=" ", flush=True)
        
        try:
            params = {"per_page": per_page, "page": page}
            params.update(params_base)
            r = requests.get(
                f"{Config.GITLAB_API}/projects/{Config.PROJECT_ID}/pipelines",
                params=params,
                headers=headers,
                timeout=60
            )
            r.raise_for_status()
            
            page_data = r.json()
            
            if not page_data:
                print("(vazia - fim)")
                break
            
            pipes.extend(page_data)
            print(f"✅ {len(page_data)} pipelines")
            
            # Verifica limite
            if max_pipelines and len(pipes) >= max_pipelines:
                pipes = pipes[:max_pipelines]
                print(f"   ⚠️  Limite de {max_pipelines} pipelines atingido")
                break
            
            # Verifica próxima página
            if 'x-next-page' not in r.headers or not r.headers['x-next-page']:
                print(f"   ℹ️  Última página alcançada")
                break
            
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro: {e}")
            break
    
    print(f"\n✅ Total coletado: {len(pipes)} pipelines")
    
    # Salva pipelines
    output_file = Config.DATA_RAW_DIR / "pipelines.json"
    with open(output_file, "w") as f:
        json.dump(pipes, f, indent=2)
    print(f"💾 Salvo em: {output_file}")
    
    # Coleta jobs
    print(f"\n📊 Coletando jobs de cada pipeline...")
    for i, pipe in enumerate(pipes, 1):
        pipe_id = pipe["id"]
        updated_at = pipe.get("updated_at") or pipe.get("created_at")
        print(f"   [{i}/{len(pipes)}] Pipeline #{pipe_id}...", end=" ", flush=True)
        
        try:
            r = requests.get(
                f"{Config.GITLAB_API}/projects/{Config.PROJECT_ID}/pipelines/{pipe_id}/jobs",
                headers=headers,
                params={"per_page": 100},
                timeout=30
            )
            r.raise_for_status()
            jobs = r.json()
            
            # Salva jobs
            jobs_file = Config.DATA_RAW_DIR / f"jobs_{pipe_id}.json"
            with open(jobs_file, "w") as f:
                json.dump(jobs, f, indent=2)
            
            print(f"✅ {len(jobs)} jobs")
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro: {e}")
            continue
    
    print(f"\n🎉 Coleta concluída!")
    print(f"   Pipelines: {len(pipes)}")
    print(f"   Diretório: {Config.DATA_RAW_DIR}")

    # Atualiza last_sync: usa o maior updated_at encontrado
    try:
        iso_times = [
            pipe.get("updated_at") or pipe.get("created_at") for pipe in pipes if pipe.get("updated_at") or pipe.get("created_at")
        ]
        if iso_times:
            max_time = max(iso_times)
            _save_last_sync(last_sync_file, {"updated_after": max_time})
            print(f"   ⏱️  last_sync atualizado: updated_after={max_time}")
    except Exception:
        pass
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch pipelines from GitLab")
    parser.add_argument("--updated-after", dest="updated_after", type=str, default=None,
                        help="ISO8601 datetime (e.g., 2025-01-01T00:00:00Z) to fetch only updated pipelines")
    parser.add_argument("--incremental", action="store_true", help="Use dados/raw/.last_sync.json as updated_after")
    args = parser.parse_args()

    success = fetch_pipelines(updated_after=args.updated_after, incremental=args.incremental)
    sys.exit(0 if success else 1)

