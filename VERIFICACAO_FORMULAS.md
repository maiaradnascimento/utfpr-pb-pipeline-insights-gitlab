# Verificação de Fórmulas Citadas no TCC

## ✅ Fórmulas Implementadas no Código

### 1. Média Amostral
**Fórmula no TCC:** $\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i$

**Localização no código:**
- `src/strategies/base.py` linha 58: `'mean': df[metric].mean()`
- `src/strategies/intelligent_strategy.py` linha 110: `'mean': df[feat].mean()`
- `src/cli/analyze.py` linha 44: `"media": serie.mean()`

**Status:** ✅ Implementada (pandas implementa esta fórmula)

---

### 2. Desvio-Padrão Amostral Corrigido
**Fórmula no TCC:** $s = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}(x_i - \bar{x})^2}$

**Localização no código:**
- `src/strategies/base.py` linha 59: `'std': df[metric].std()`
- `src/strategies/intelligent_strategy.py` linha 111: `'std': df[feat].std()`
- `src/cli/analyze.py` linha 46: `"desvio_padrao": serie.std()`

**Status:** ✅ Implementada (pandas usa `ddof=1` por padrão, que é a fórmula corrigida)

---

### 3. Z-Score
**Fórmula no TCC:** $z = \frac{x - \mu}{\sigma}$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 141: `z_score = (value - t['mean']) / t['std']`

**Status:** ✅ Implementada

---

### 4. Z-Score por Cluster
**Fórmula no TCC:** $z = \frac{x - \mu_{cluster}}{\sigma_{cluster}}$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 141: O z-score é calculado usando média e desvio-padrão do cluster (thresholds são calculados por cluster)

**Status:** ✅ Implementada (thresholds são aprendidos por cluster, então o z-score é calculado usando estatísticas do cluster)

---

### 5. Taxa de Falha
**Fórmula no TCC:** $\frac{fails}{builds}$

**Localização no código:**
- `src/etl/incremental.py` linha 534: `features['fail_rate'] = features['fails'] / (features['builds'] + 1)`
- `src/core/models.py` linha 95: `self.fail_rate = self.failed_jobs / self.total_jobs`
- `src/cli/normalize.py` linha 99: `.groupby("pipeline_id")["fail"].mean().rename("fail_rate")`

**Status:** ✅ Implementada

---

### 6. Z-Score Normalization (StandardScaler)
**Fórmula no TCC:** $z = \frac{x - \mu}{\sigma}$ (normalização)

**Localização no código:**
- `src/ml/train.py` linha 115-116: `scaler = StandardScaler()` e `X_scaled = scaler.fit_transform(X)`
- `src/strategies/intelligent_strategy.py`: Features são normalizadas antes do clustering

**Status:** ✅ Implementada (StandardScaler do scikit-learn implementa esta fórmula)

---

### 7. Ganho Estimado
**Fórmula no TCC:** $\Delta = x_{atual} - p50_{cluster}$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 219: `gain = feat_info['value'] - feat_info['p50'] if feat_info['value'] > feat_info['p50'] else 0`

**Status:** ✅ Implementada

---

### 8. Ganho Percentual
**Fórmula no TCC:** $\Delta\% = \frac{\Delta}{x_{atual}} \times 100$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 220: `gain_pct = (gain / feat_info['value'] * 100) if feat_info['value'] > 0 else 0`

**Status:** ✅ Implementada

---

## ⚠️ Fórmulas Implementadas via Bibliotecas (Não Explícitas no Código)

### 9. Isolation Forest Score
**Fórmula no TCC:** $s(x, \psi) = 2^{-\frac{E(h(x))}{c(\psi)}}$

**Localização no código:**
- `src/ml/train.py` linha 129: `scores = model.score_samples(X_scaled)`
- `src/strategies/intelligent_strategy.py` linha 66: `scores = self.anomaly_detector.score_samples(X)`

**Status:** ⚠️ Implementada via scikit-learn (a fórmula específica está dentro da biblioteca, não no código do projeto)

**Observação:** Esta é uma implementação interna do scikit-learn, então está correta, mas a fórmula não está explicitamente no código.

---

### 10. K-Means Função Objetivo
**Fórmula no TCC:** $J = \sum_{i=1}^{n}\sum_{j=1}^{k} w_{ij}||x_i - \mu_j||^2$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 33-36: `KMeans` do scikit-learn

**Status:** ⚠️ Implementada via scikit-learn (a fórmula específica está dentro da biblioteca, não no código do projeto)

**Observação:** Esta é uma implementação interna do scikit-learn, então está correta, mas a fórmula não está explicitamente no código.

---

### 11. Distância Euclidiana
**Fórmula no TCC:** $d(x, y) = \sqrt{\sum_{i=1}^{n}(x_i - y_i)^2}$

**Localização no código:**
- `src/strategies/intelligent_strategy.py` linha 33-36: KMeans do scikit-learn usa distância euclidiana por padrão

**Status:** ⚠️ Implementada via scikit-learn (KMeans usa distância euclidiana por padrão, mas não está explicitamente no código)

**Observação:** KMeans do scikit-learn usa distância euclidiana por padrão, então está correta, mas a fórmula não está explicitamente no código.

---

## ❌ Fórmulas NÃO Implementadas no Código

### 12. Ranking Ponderado
**Fórmula no TCC:** $rank = \alpha \cdot |score_{IF}| + (1-\alpha) \cdot |z-score|$, onde $\alpha=0.7$

**Localização no código:**
- ❌ **NÃO ENCONTRADA**

**Status:** ❌ **NÃO IMPLEMENTADA**

**Observação:** O código em `src/strategies/intelligent_strategy.py` linha 211-214 usa apenas o z-score absoluto para determinar a feature principal:
```python
main_feature = max(
    context.items(),
    key=lambda x: abs(x[1].get('z_score', 0))
)
```

Não há combinação ponderada com o score do Isolation Forest. O TCC menciona esta fórmula na seção de metodologia (cap-metodologia.tex linha 50), mas ela não está implementada.

---

## Resumo

- **Fórmulas implementadas explicitamente:** 8
- **Fórmulas implementadas via bibliotecas:** 3
- **Fórmulas não implementadas:** 1 (Ranking Ponderado)

## Recomendações

1. **Remover ou corrigir a menção ao ranking ponderado** no TCC, OU
2. **Implementar a fórmula de ranking ponderado** no código em `src/strategies/intelligent_strategy.py`

