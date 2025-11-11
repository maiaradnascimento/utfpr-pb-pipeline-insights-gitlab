"""
Experimento Controlado: Injeção de Anomalias
Objetivo específico: Validar que o modelo detecta corretamente pipelines com comportamento anômalo

Este script:
1. Cria um lote de pipelines "lentos" marcados (SLOW_TEST=1)
2. Mistura com pipelines normais
3. Executa detecção de anomalias
4. Calcula taxa de detecção (precisão/recall)
5. Gera relatório de validação
"""
import pandas as pd, numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import os
from pathlib import Path
try:
    from src.core.config import Config
    Config.validate()
    FIG_DIR = Config.FIGURES_DIR
    PROC_DIR = Config.DATA_PROCESSED_DIR
except Exception:
    # Fallback
    PROC_DIR = Path("dados/processed")
    FIG_DIR = PROC_DIR / "figuras"

os.makedirs(PROC_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

print("="*70)
print("🧪 EXPERIMENTO CONTROLADO - VALIDAÇÃO DO MODELO DE DETECÇÃO")
print("="*70)

# ====== 1. CARREGA OU GERA DADOS BASE ======
print("\n📊 Carregando dados base...")
if os.path.exists(str(PROC_DIR / "pipelines.csv")):
    df_base = pd.read_csv(PROC_DIR / "pipelines.csv")
    print(f"✅ {len(df_base)} pipelines carregados")
else:
    print("⚠️  Gerando dados sintéticos para experimento...")
    # Gera dados sintéticos
    import random
    random.seed(42)
    
    pipelines = []
    for i in range(1, 101):
        build = abs(random.gauss(300, 60))
        test = abs(random.gauss(420, 120))
        deploy = abs(random.gauss(180, 40))
        
        pipelines.append({
            "pipeline_id": i,
            "stage_build": build,
            "stage_test": test,
            "stage_deploy": deploy,
            "dur_total": build + test + deploy,
            "fail_rate": 0 if random.random() > 0.15 else random.uniform(0.2, 0.5),
            "max_retries": 0 if random.random() > 0.1 else random.randint(1, 3),
            "status": "success",
            "slow_injected": False
        })
    
    df_base = pd.DataFrame(pipelines)
    print(f"✅ {len(df_base)} pipelines sintéticos gerados")

# Adiciona coluna slow_injected se não existir
if "slow_injected" not in df_base.columns:
    df_base["slow_injected"] = False

# Garante que colunas necessárias existem
for col in ["stage_build", "stage_test", "stage_deploy", "max_retries", "fail_rate"]:
    if col not in df_base.columns:
        df_base[col] = 0 if col != "fail_rate" else 0.0

# ====== 2. INJEÇÃO DE ANOMALIAS CONTROLADAS ======
print("\n💉 Injetando anomalias controladas...")

# Identifica quais colunas de stage estão disponíveis
available_stages = [c for c in ["stage_build", "stage_test", "stage_deploy"] if c in df_base.columns and df_base[c].sum() > 0]
print(f"   Estágios disponíveis: {', '.join(available_stages) if available_stages else 'Nenhum (usando dur_total)'}")

# Parâmetros do experimento
NUM_ANOMALIAS_INJETAR = max(10, int(len(df_base) * 0.15))  # 15% do dataset
print(f"   Quantidade a injetar: {NUM_ANOMALIAS_INJETAR} pipelines (~15%)")

# Seleciona pipelines aleatórios para injetar anomalia
np.random.seed(42)
indices_anomalias = np.random.choice(df_base.index, size=NUM_ANOMALIAS_INJETAR, replace=False)

# Cria cópia para experimento
df_exp = df_base.copy()

# Injeta anomalias de diferentes tipos
for idx in indices_anomalias:
    # Se não temos estágios específicos, usa apenas dur_total e retries
    if not available_stages:
        tipo_anomalia = np.random.choice(["slow_all", "high_retry"])
    else:
        tipo_anomalia = np.random.choice(["slow_test", "slow_build", "slow_all", "high_retry"])
    
    if tipo_anomalia == "slow_test" and "stage_test" in available_stages:
        # Aumenta drasticamente o tempo de teste (2-3x)
        if df_exp.loc[idx, "stage_test"] > 0:
            df_exp.loc[idx, "stage_test"] *= np.random.uniform(2.0, 3.0)
            df_exp.loc[idx, "slow_type"] = "test"
        else:
            tipo_anomalia = "slow_all"
        
    if tipo_anomalia == "slow_build" and "stage_build" in available_stages:
        # Aumenta drasticamente o tempo de build (2-3x)
        if df_exp.loc[idx, "stage_build"] > 0:
            df_exp.loc[idx, "stage_build"] *= np.random.uniform(2.0, 3.0)
            df_exp.loc[idx, "slow_type"] = "build"
        else:
            tipo_anomalia = "slow_all"
        
    if tipo_anomalia == "slow_all":
        # Aumenta dur_total ou todos os estágios disponíveis (1.5-2x)
        fator = np.random.uniform(1.5, 2.0)
        if available_stages:
            for stage in available_stages:
                if df_exp.loc[idx, stage] > 0:
                    df_exp.loc[idx, stage] *= fator
        else:
            # Se não tem estágios, aumenta dur_total diretamente
            if df_exp.loc[idx, "dur_total"] > 0:
                df_exp.loc[idx, "dur_total"] *= fator
        df_exp.loc[idx, "slow_type"] = "all"
        
    if tipo_anomalia == "high_retry":
        # Aumenta retries e fail rate
        df_exp.loc[idx, "max_retries"] = np.random.randint(3, 6)
        df_exp.loc[idx, "fail_rate"] = np.random.uniform(0.4, 0.8)
        df_exp.loc[idx, "slow_type"] = "retry"
    
    # Marca como anomalia injetada (ground truth)
    df_exp.loc[idx, "slow_injected"] = True
    
    # Recalcula duração total se tiver estágios
    if available_stages:
        stage_sum = sum([df_exp.loc[idx, stage] for stage in available_stages])
        if stage_sum > 0:
            df_exp.loc[idx, "dur_total"] = stage_sum

# Adiciona coluna slow_type para os normais
if "slow_type" not in df_exp.columns:
    df_exp["slow_type"] = "normal"
df_exp.loc[df_exp["slow_injected"] == False, "slow_type"] = "normal"

print(f"✅ {df_exp['slow_injected'].sum()} anomalias injetadas")
print(f"   Distribuição por tipo:")
for tipo in df_exp[df_exp["slow_injected"]]["slow_type"].value_counts().items():
    print(f"      • {tipo[0]}: {tipo[1]} pipelines")

# ====== 3. DETECÇÃO DE ANOMALIAS ======
print("\n🔍 Executando detecção de anomalias...")

feat_cols = [c for c in ["dur_total", "stage_build", "stage_test", "stage_deploy", "fail_rate", "max_retries"] 
             if c in df_exp.columns]
X = df_exp[feat_cols].fillna(0)

# Testa com diferentes configurações
configs = [
    {"nome": "Conservador", "contamination": 0.05},
    {"nome": "Moderado", "contamination": 0.10},
    {"nome": "Agressivo", "contamination": 0.15}
]

resultados_configs = []

for config in configs:
    iso = IsolationForest(
        random_state=42,
        n_estimators=200,
        contamination=config['contamination']
    )
    
    predictions = iso.fit_predict(X)
    
    # Converte para formato binário (0=normal, 1=anomalia)
    y_true = df_exp["slow_injected"].astype(int)
    y_pred = (predictions == -1).astype(int)
    
    # Calcula métricas
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    
    precisao = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precisao * recall) / (precisao + recall) if (precisao + recall) > 0 else 0
    acuracia = (tp + tn) / len(df_exp)
    
    resultados_configs.append({
        "configuracao": config["nome"],
        "contamination": config["contamination"],
        "verdadeiros_positivos": int(tp),
        "falsos_positivos": int(fp),
        "verdadeiros_negativos": int(tn),
        "falsos_negativos": int(fn),
        "precisao": round(precisao, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "acuracia": round(acuracia, 3)
    })
    
    print(f"\n   {config['nome']} (contamination={config['contamination']}):")
    print(f"      TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
    print(f"      Precisão: {precisao:.2%} | Recall: {recall:.2%} | F1: {f1:.3f}")

# Salva resultados
resultados_df = pd.DataFrame(resultados_configs)
resultados_df.to_csv(PROC_DIR / "experimento_validacao.csv", index=False)

# ====== 4. ANÁLISE DETALHADA - CONFIGURAÇÃO MODERADA ======
print("\n" + "="*70)
print("📊 ANÁLISE DETALHADA - Configuração Moderada")
print("="*70)

iso_moderado = IsolationForest(random_state=42, n_estimators=200, contamination=0.10)
predictions_moderado = iso_moderado.fit_predict(X)
scores_moderado = iso_moderado.decision_function(X)

df_exp["anomalia_detectada"] = (predictions_moderado == -1)
df_exp["anomalia_score"] = scores_moderado

y_true = df_exp["slow_injected"].astype(int)
y_pred = df_exp["anomalia_detectada"].astype(int)

print("\n📈 Matriz de Confusão:")
cm = confusion_matrix(y_true, y_pred)
print(f"\n                 Predito Negativo  |  Predito Positivo")
print(f"Real Negativo:      {cm[0,0]:5d}        |      {cm[0,1]:5d}    (FP)")
print(f"Real Positivo:      {cm[1,0]:5d}  (FN)  |      {cm[1,1]:5d}    (TP)")

print("\n📊 Métricas de Performance:")
print(classification_report(y_true, y_pred, target_names=["Normal", "Anomalia"]))

# ====== 5. VISUALIZAÇÕES ======

# 5.1 Matriz de confusão
fig, ax = plt.subplots(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', square=True, ax=ax,
            xticklabels=['Predito: Normal', 'Predito: Anomalia'],
            yticklabels=['Real: Normal', 'Real: Anomalia'])
ax.set_title('Matriz de Confusão - Experimento Controlado', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(FIG_DIR / "experimento_matriz_confusao.png", dpi=300)
plt.close()
print("\n✅ Matriz de confusão salva em experimento_matriz_confusao.png")

# 5.2 Comparação de métricas entre configurações
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Precisão
axes[0, 0].bar(resultados_df["configuracao"], resultados_df["precisao"], color='steelblue')
axes[0, 0].set_ylabel('Precisão', fontsize=11)
axes[0, 0].set_title('Precisão por Configuração', fontsize=12, fontweight='bold')
axes[0, 0].set_ylim(0, 1)
axes[0, 0].grid(True, alpha=0.3, axis='y')

# Recall
axes[0, 1].bar(resultados_df["configuracao"], resultados_df["recall"], color='coral')
axes[0, 1].set_ylabel('Recall', fontsize=11)
axes[0, 1].set_title('Recall por Configuração', fontsize=12, fontweight='bold')
axes[0, 1].set_ylim(0, 1)
axes[0, 1].grid(True, alpha=0.3, axis='y')

# F1-Score
axes[1, 0].bar(resultados_df["configuracao"], resultados_df["f1_score"], color='green')
axes[1, 0].set_ylabel('F1-Score', fontsize=11)
axes[1, 0].set_title('F1-Score por Configuração', fontsize=12, fontweight='bold')
axes[1, 0].set_ylim(0, 1)
axes[1, 0].grid(True, alpha=0.3, axis='y')

# Acurácia
axes[1, 1].bar(resultados_df["configuracao"], resultados_df["acuracia"], color='purple')
axes[1, 1].set_ylabel('Acurácia', fontsize=11)
axes[1, 1].set_title('Acurácia por Configuração', fontsize=12, fontweight='bold')
axes[1, 1].set_ylim(0, 1)
axes[1, 1].grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig(FIG_DIR / "experimento_metricas_comparacao.png", dpi=300)
plt.close()
print("✅ Comparação de métricas salva em experimento_metricas_comparacao.png")

# 5.3 Distribuição de scores
fig, ax = plt.subplots(figsize=(10, 6))
scores_normais = df_exp[~df_exp["slow_injected"]]["anomalia_score"]
scores_anomalias = df_exp[df_exp["slow_injected"]]["anomalia_score"]

ax.hist(scores_normais, bins=30, alpha=0.6, label='Pipelines Normais', color='blue', edgecolor='black')
ax.hist(scores_anomalias, bins=30, alpha=0.6, label='Anomalias Injetadas', color='red', edgecolor='black')
ax.set_xlabel('Anomalia Score', fontsize=12)
ax.set_ylabel('Frequência', fontsize=12)
ax.set_title('Distribuição de Scores: Normal vs Anomalias', fontsize=14, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig(FIG_DIR / "experimento_distribuicao_scores.png", dpi=300)
plt.close()
print("✅ Distribuição de scores salva em experimento_distribuicao_scores.png")

# ====== 6. ANÁLISE DE FALSOS POSITIVOS E FALSOS NEGATIVOS ======
print("\n" + "="*70)
print("🔬 ANÁLISE DE ERROS")
print("="*70)

# Falsos Positivos (detectou anomalia mas era normal)
falsos_positivos = df_exp[(~df_exp["slow_injected"]) & (df_exp["anomalia_detectada"])]
print(f"\n❌ Falsos Positivos: {len(falsos_positivos)}")
if len(falsos_positivos) > 0:
    print("   Pipelines normais incorretamente classificados como anomalias:")
    for _, fp in falsos_positivos.head(5).iterrows():
        print(f"      Pipeline #{int(fp['pipeline_id'])}: dur_total={fp['dur_total']:.0f}s, score={fp['anomalia_score']:.3f}")

# Falsos Negativos (não detectou mas era anomalia)
falsos_negativos = df_exp[(df_exp["slow_injected"]) & (~df_exp["anomalia_detectada"])]
print(f"\n❌ Falsos Negativos: {len(falsos_negativos)}")
if len(falsos_negativos) > 0:
    print("   Anomalias injetadas que NÃO foram detectadas:")
    for _, fn in falsos_negativos.head(5).iterrows():
        print(f"      Pipeline #{int(fn['pipeline_id'])}: tipo={fn['slow_type']}, dur_total={fn['dur_total']:.0f}s, score={fn['anomalia_score']:.3f}")

# ====== 7. SALVAR DATASET COMPLETO ======
df_exp.to_csv(PROC_DIR / "experimento_dataset_completo.csv", index=False)

# ====== 8. RESUMO FINAL ======
print("\n" + "="*70)
print("✅ EXPERIMENTO CONTROLADO CONCLUÍDO")
print("="*70)
print(f"\n📊 Dataset do Experimento:")
print(f"   Total de pipelines: {len(df_exp)}")
print(f"   Anomalias injetadas (ground truth): {df_exp['slow_injected'].sum()}")
print(f"   Anomalias detectadas: {df_exp['anomalia_detectada'].sum()}")

melhor_config = resultados_df.loc[resultados_df["f1_score"].idxmax()]
print(f"\n🏆 Melhor Configuração: {melhor_config['configuracao']}")
print(f"   F1-Score: {melhor_config['f1_score']:.3f}")
print(f"   Precisão: {melhor_config['precisao']:.3f}")
print(f"   Recall: {melhor_config['recall']:.3f}")

print(f"\n📄 Arquivos Gerados:")
print(f"   • {PROC_DIR}/experimento_validacao.csv")
print(f"   • {PROC_DIR}/experimento_dataset_completo.csv")
print(f"   • {FIG_DIR}/experimento_matriz_confusao.png")
print(f"   • {FIG_DIR}/experimento_metricas_comparacao.png")
print(f"   • {FIG_DIR}/experimento_distribuicao_scores.png")

print("\n" + "="*70)
print("🎯 CONCLUSÃO: O modelo foi validado com dados controlados!")
print("="*70)

