"""
Gerador de Dados Sintéticos

Gera dados de exemplo para testes sem necessidade de GitLab real.
"""

import os
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate_synthetic_data(n_pipelines=300, output_dir="dados/raw", seed=42):
    """
    Gera dados sintéticos de pipelines e jobs
    
    Args:
        n_pipelines: Número de pipelines a gerar
        output_dir: Diretório de saída
        seed: Seed para reprodutibilidade
    
    Returns:
        tuple: (path_pipelines, path_jobs)
    """
    # Setup
    os.makedirs(output_dir, exist_ok=True)
    random.seed(seed)
    base_time = datetime.now() - timedelta(days=15)
    
    # Gera pipelines
    pipelines = []
    for i in range(1, n_pipelines + 1):
        timestamp = (base_time + timedelta(minutes=i * 60)).isoformat()
        status = random.choices(
            ["success", "failed", "canceled"],
            weights=[0.75, 0.2, 0.05]
        )[0]
        pipelines.append([i, timestamp, status])
    
    # Salva pipelines
    pipeline_path = os.path.join(output_dir, "pipelines_sintetico.csv")
    with open(pipeline_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pipeline_id", "timestamp", "status"])
        writer.writerows(pipelines)
    
    # Gera jobs
    stages = ["build", "test", "deploy"]
    jobs_path = os.path.join(output_dir, "jobs_sintetico.csv")
    
    with open(jobs_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "pipeline_id", "job_id", "stage", "duration_sec",
            "status", "retries", "error_text"
        ])
        
        job_id = 1
        for pipeline_id, _, pipeline_status in pipelines:
            # Durações médias por stage (com variação)
            build_duration = abs(random.gauss(300, 60))
            test_duration = abs(random.gauss(420, 120))
            deploy_duration = abs(random.gauss(180, 40))
            
            # Ocasionalmente cria anomalias
            if random.random() < 0.08:  # 8% de testes lentos
                test_duration *= random.uniform(1.8, 2.4)
            if random.random() < 0.06:  # 6% de builds lentos
                build_duration *= random.uniform(1.7, 2.2)
            
            # Cria jobs para cada stage
            for stage, duration in [
                ("build", build_duration),
                ("test", test_duration),
                ("deploy", deploy_duration)
            ]:
                # Status do job
                if pipeline_status == "success":
                    job_status = "success"
                else:
                    job_status = random.choice(["failed", "success"])
                
                # Retries e erros
                retries = 0 if job_status == "success" else random.choice([0, 1, 2, 3])
                error_text = "" if job_status == "success" else random.choice([
                    "timeout",
                    "dependency not found",
                    "network flakiness",
                    "repo 503"
                ])
                
                writer.writerow([
                    pipeline_id,
                    job_id,
                    stage,
                    round(duration, 1),
                    job_status,
                    retries,
                    error_text
                ])
                job_id += 1
    
    print(f"✅ Dados sintéticos gerados:")
    print(f"   Pipelines: {pipeline_path}")
    print(f"   Jobs: {jobs_path}")
    print(f"   Total: {n_pipelines} pipelines, {job_id-1} jobs")
    
    return pipeline_path, jobs_path


if __name__ == "__main__":
    generate_synthetic_data()

