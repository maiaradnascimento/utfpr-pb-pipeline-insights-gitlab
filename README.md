# Pipeline Optimizer - IA para Otimização de Pipelines DevOps

Sistema de análise inteligente de pipelines CI/CD usando Machine Learning para detectar anomalias e gerar recomendações automáticas de otimização.

## 🎯 Propósito

Este sistema coleta dados de execução de pipelines GitLab via API, aplica algoritmos de Machine Learning (Isolation Forest, K-Means) para identificar anomalias e gera recomendações automáticas para:

- **Reduzir tempo de execução** (cache, paralelização)
- **Melhorar confiabilidade** (retry, timeout)
- **Otimizar recursos** (configuração de stages e jobs)

## ✨ Características

- ✅ **Arquitetura Incremental e Idempotente** - Processa apenas novos dados, não reprocessa tudo
- ✅ **Versionamento de Modelos** - Model Registry com versionamento de modelos, transformadores e feature schemas
- ✅ **Feature Store** - Cache offline/online de features para inferência rápida
- ✅ **API REST** - FastAPI com endpoints para predições, métricas, erros e inferência
- ✅ **UI Interativa** - Streamlit com filtros de data e visualizações
- ✅ **Análise de Erros** - Detalhamento de falhas com agregação por tipo e job
- ✅ **Machine Learning** - Isolation Forest + K-Means para detecção de anomalias
- ✅ **Watermark Pattern** - Processamento incremental com controle de timestamp
- ✅ **Janelas Deslizantes** - Reprocessa apenas últimos N dias para corrigir atrasos

## 🚀 Início Rápido

### Opção 1: Usar Imagem do Docker Hub com Dados (Mais Rápido!)

```bash
# 1. Baixe a imagem com dados já incluídos
docker pull maiaradnascimento/pipeline-optimizer:latest-with-data

# 2. Baixe o docker-compose.with-data.yml do repositório
# Ou use o exemplo completo abaixo

# 3. Suba tudo (banco + API + UI)
export DOCKER_USER="maiaradnascimento"
export VERSION="latest-with-data"
docker-compose -f docker-compose.with-data.yml up -d

# 4. Aguarde ~15 segundos e acesse:
# API: http://localhost:8000/docs
# UI: http://localhost:8501
```

**Vantagens:**
- ✅ Não precisa processar dados (já vem tudo pronto)
- ✅ 605+ pipelines já processados
- ✅ Modelos já treinados
- ✅ UI e API funcionando imediatamente

### Opção 2: Build Local

```bash
# 1. Configure as credenciais
export PROJECT_ID="seu_project_id"
export TOKEN="seu_token"

# 2. Construa a imagem Docker
make build

# 3. Execute o pipeline
make processar
```

### Opção 3: Código Fonte

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/pipeline-optimizer.git
cd pipeline-optimizer

# 2. Instale dependências
pip install -r requirements.txt

# 3. Configure credenciais
export PROJECT_ID="seu_project_id"
export TOKEN="seu_token"

# 4. Execute
python src/cli/fetch.py --incremental
python src/cli/etl_incremental.py
```

### Pré-requisitos

- Docker e Docker Compose (para uso com Docker)
- Python 3.11+ (para uso direto do código)
- Token do GitLab com permissão `read_api`
- Project ID do projeto GitLab a analisar

## 🐳 Docker Hub

### Publicar Imagem com Dados do Banco (Recomendado)

Para publicar a imagem **com os dados do banco já incluídos**:

```bash
# 1. Faça login no Docker Hub
docker login

# 2. Configure seu usuário
export DOCKER_USER="seu-usuario"
export VERSION="v1.0.0"  # ou "latest"

# 3. Exporte o banco e publique tudo de uma vez
make docker-push-with-data
```

Isso vai:
- Exportar o banco de dados automaticamente
- Construir a imagem com código + modelos + dados + backup do banco
- Publicar no Docker Hub

**📚 Guia completo**: Veja `PUBLICAR_DOCKER_HUB.md` para instruções detalhadas.

### Publicar Imagem no Docker Hub (sem dados)

```bash
# 1. Faça login no Docker Hub
docker login

# 2. Configure o nome da imagem (substitua 'seu-usuario' pelo seu username)
export DOCKER_USER="seu-usuario"
export IMAGE_NAME="pipeline-optimizer"
export VERSION="latest"  # ou "v1.0.0", etc.

# 3. Build da imagem
docker build -t $DOCKER_USER/$IMAGE_NAME:$VERSION .

# 4. Tag adicional para 'latest' (se não for a versão latest)
docker tag $DOCKER_USER/$IMAGE_NAME:$VERSION $DOCKER_USER/$IMAGE_NAME:latest

# 5. Push para Docker Hub
docker push $DOCKER_USER/$IMAGE_NAME:$VERSION
docker push $DOCKER_USER/$IMAGE_NAME:latest

# Ou use o Makefile (recomendado)
export DOCKER_USER="seu-usuario"
make docker-push  # Faz build e push automaticamente
```

### Baixar e Usar a Imagem do Docker Hub

#### Opção A: Imagem com Dados (Recomendado - Tudo Pronto!)

A imagem `-with-data` inclui código, modelos, dados processados e backup completo do banco. **Ideal para uso imediato sem precisar processar dados.**

```bash
# 1. Baixe a imagem com dados
docker pull maiaradnascimento/pipeline-optimizer:latest-with-data

# 2. Baixe o docker-compose.with-data.yml do repositório
# Ou crie manualmente (veja exemplo abaixo)

# 3. Configure e suba tudo (banco + API + UI)
export DOCKER_USER="maiaradnascimento"
export VERSION="latest-with-data"
docker-compose -f docker-compose.with-data.yml up -d

# 4. Aguarde ~15 segundos para o banco ser restaurado
sleep 15

# 5. Acesse os serviços
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
# UI: http://localhost:8501
```

**O que está incluído:**
- ✅ Código fonte completo
- ✅ Modelos treinados (model_v2.pkl, model_v3.pkl, etc.)
- ✅ Dados processados
- ✅ Backup completo do banco (605+ pipelines)
- ✅ Script de inicialização automática

#### Opção B: Imagem sem Dados (Para Processar Seus Próprios Dados)

```bash
# 1. Baixe a imagem
docker pull maiaradnascimento/pipeline-optimizer:latest

# 2. Crie um docker-compose.yml
cat > docker-compose.yml << 'EOF'
name: pipeline-optimizer

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: pipeline_optimizer
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/migrations:/docker-entrypoint-initdb.d

  pipeline-optimizer-scripts:
    image: maiaradnascimento/pipeline-optimizer:latest
    depends_on:
      - postgres
    environment:
      PROJECT_ID: ${PROJECT_ID}
      TOKEN: ${TOKEN}
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: pipeline_optimizer
      DB_USER: postgres
      DB_PASS: postgres
    volumes:
      - ./dados:/app/dados
      - ./models:/app/models

volumes:
  postgres_data:
EOF

# 3. Configure credenciais
export PROJECT_ID="seu_project_id"
export TOKEN="seu_token"

# 4. Inicie o banco
docker-compose up -d postgres

# 5. Execute comandos
docker-compose run --rm -e PROJECT_ID=$PROJECT_ID -e TOKEN=$TOKEN \
  pipeline-optimizer-scripts python src/cli/fetch.py --incremental
```

#### Exemplo Completo: docker-compose.with-data.yml

```yaml
name: pipeline-optimizer-with-data

services:
  postgres:
    image: postgres:15-alpine
    container_name: pipeline-optimizer-postgres
    environment:
      POSTGRES_DB: pipeline_optimizer
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  pipeline-optimizer-scripts:
    image: maiaradnascimento/pipeline-optimizer:latest-with-data
    container_name: pipeline-optimizer-scripts
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: pipeline_optimizer
      DB_USER: postgres
      DB_PASS: postgres
    command: /app/scripts/init-db.sh && echo "✅ Banco inicializado!" && tail -f /dev/null

  api:
    image: maiaradnascimento/pipeline-optimizer:latest-with-data
    container_name: pipeline-optimizer-api
    depends_on:
      - postgres
      - pipeline-optimizer-scripts
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: pipeline_optimizer
      DB_USER: postgres
      DB_PASS: postgres
    ports:
      - "8000:8000"
    command: /app/scripts/init-db.sh && uvicorn src.api.app:app --host 0.0.0.0 --port 8000

  ui:
    image: maiaradnascimento/pipeline-optimizer:latest-with-data
    container_name: pipeline-optimizer-ui
    depends_on:
      - api
    environment:
      API_BASE_URL: http://api:8000
    ports:
      - "8501:8501"
    command: streamlit run src/ui/app_incremental.py --server.address 0.0.0.0 --server.port 8501

volumes:
  postgres_data:
```

**📚 Guia completo**: Veja `COMO_USAR_IMAGEM_DOCKER_HUB.md` para instruções detalhadas.

### Comandos Makefile para Docker Hub

Os comandos já estão disponíveis no `Makefile`:

```bash
# Configure seu usuário do Docker Hub
export DOCKER_USER="seu-usuario"

# Build da imagem
make docker-build

# Push para Docker Hub (faz build automaticamente)
make docker-push

# Pull da imagem do Docker Hub
make docker-pull

# Build de versão específica
VERSION=v1.0.0 make docker-build
VERSION=v1.0.0 make docker-push
```

## 📋 Comandos Disponíveis

### Processamento

```bash
make processar              # Pipeline completo (dados reais, todos os pipelines)
make processar-rapido      # Pipeline rápido (100 pipelines)
make processar-sintetico   # Pipeline com dados sintéticos (demo)
```

### Setup

```bash
make build                 # Constrói imagem Docker
make up                    # Sobe tudo (banco + API + UI incremental)
make down                  # Para tudo
```

### API

```bash
make api-start            # Inicia API FastAPI (http://localhost:8000)
make api-stop             # Para API FastAPI
make api-logs             # Mostra logs da API
```

### UI

```bash
make ui                   # Inicia UI incremental (http://localhost:8501)
# Nota: A UI básica foi substituída pela UI incremental
```

### Docker Hub

```bash
make docker-build         # Build da imagem Docker
make docker-push          # Push para Docker Hub (faz build automaticamente)
make docker-pull          # Pull da imagem do Docker Hub

# Configure antes:
export DOCKER_USER="seu-usuario"
```

### Limpeza

```bash
make clean                # Remove containers e volumes Docker
```

### Distribuição

```bash
make export-db            # Exporta banco de dados para backup
make import-db FILE=      # Importa banco de dados (ex: FILE=backup.sql.gz)
make dist                 # Cria pacote completo (banco + modelos + código)
```

### Ajuda

```bash
make help                 # Mostra todos os comandos disponíveis
```

## 🏗️ Arquitetura

### Componentes Principais

1. **ETL Incremental** (`src/etl/incremental.py`)
   - Watermark por fonte (último timestamp processado)
   - Append-only em raw tables
   - UPSERT idempotente em agregados/features
   - Janela deslizante (reprocessa apenas últimos N dias)

2. **Model Registry** (`src/ml/registry.py`)
   - Versionamento de modelos (`model_v{N}.pkl`)
   - Versionamento de transformadores (`scaler_v{N}.pkl`)
   - Versionamento de feature schemas (`feature_schema_v{N}.json`)

3. **Feature Store**
   - `features_offline` - Histórico completo
   - `features_online` - Cache atual para inferência rápida

4. **API REST** (`src/api/app.py`)
   - `GET /predictions` - Busca predições com filtros
   - `POST /infer/{run_id}` - Inferência individual
   - `GET /metrics` - Métricas diárias
   - `GET /model/info` - Informações do modelo atual

5. **UI Streamlit** (`src/ui/app_incremental.py`)
   - Filtros de data (from/to)
   - Modo Atual vs Snapshot
   - Visualização de predições e métricas
   - Execução de ETL e treino

## 📊 Fluxo de Dados

```
GitLab API
    ↓
[Coleta Incremental] → pipelines_raw / jobs_raw (append-only)
    ↓
[ETL Incremental] → metrics_daily (UPSERT)
    ↓
[Feature Engineering] → features_offline / features_online
    ↓
[Model Training] → model_v{N}.pkl + transformers
    ↓
[Inference] → predictions (imutável por run_id + model_version)
```

## 🗄️ Banco de Dados

### Setup Inicial

```bash
# Via Docker (recomendado)
make build
make processar  # Cria banco automaticamente

# Ou manualmente
createdb pipeline_optimizer
psql -d pipeline_optimizer -f sql/migrations/001_initial_schema.sql
```

### Estrutura de Tabelas

- **`processing_watermarks`** - Controla último timestamp processado
- **`pipelines_raw` / `jobs_raw`** - Dados brutos (append-only)
- **`metrics_daily`** - Agregados diários (UPSERT idempotente)
- **`features_offline` / `features_online`** - Feature store
- **`predictions`** - Predições (imutáveis por run_id + model_version)
- **`predictions_backfill`** - Backfill histórico
- **`model_registry`** - Versionamento de modelos
- **`kv_config`** - Configurações (MODEL_CURRENT, etc)

### ⚠️ Importante: Como Funcionam as Predições

**Por que há apenas 8 predições quando há muitos registros?**

O sistema gera predições por **job** (não por pipeline individual):

1. **Agregação por Job**: O sistema agrega todos os pipelines/jobs e cria uma feature por `job_name` único
2. **Entity Key**: Cada feature é identificada por `entity_key = "project_id:job_name"`
3. **Predições**: Uma predição é gerada para cada `entity_key` único em `features_online`

**Exemplo:**
- 100 pipelines executados
- 8 jobs únicos (ex: `build`, `test`, `deploy`, `lint`, `security`, `docker`, `k8s`, `notify`)
- **Resultado**: 8 features e 8 predições (uma para cada job)

Isso é o comportamento esperado! As predições representam o comportamento agregado de cada job ao longo do tempo, não execuções individuais de pipelines.

## 🔄 Processamento Incremental

### Como Funciona

1. **Watermark**: Armazena último timestamp processado por fonte
2. **Append-only**: Dados raw nunca são sobrescritos
3. **UPSERT**: Agregados e features são atualizados idempotentemente
4. **Janela Deslizante**: Reprocessa apenas últimos N dias para corrigir atrasos

### Executar ETL Incremental

```bash
# Via Makefile (recomendado)
make processar

# Ou diretamente
python src/cli/etl_incremental.py --reprocess-days 3
```

## 🎓 Model Registry

### Treinar Modelo

```bash
# Via Python
python src/ml/train.py \
    --window-start 2025-01-01 \
    --window-end 2025-12-31

# O modelo será salvo como model_v{N+1}.pkl
```

### Backfill

```bash
# Re-scora predições históricas
python src/ml/backfill.py \
    --model-version 2 \
    --days 30
```

## 🔌 API REST

### Iniciar API

```bash
make api-start
# Acesse: http://localhost:8000/docs
```

### Endpoints Principais

- `GET /healthz` - Health check
- `GET /predictions?from=2025-01-01&to=2025-12-31&mode=actual` - Busca predições
- `POST /infer/{run_id}` - Gera predição para um run_id
- `POST /predictions/generate` - Gera predições em lote para todas as features_online
- `GET /metrics?from=2025-01-01&to=2025-12-31` - Métricas diárias
- `GET /errors?from=2025-01-01&to=2025-12-31&limit=100` - Lista erros de pipelines/jobs
- `GET /errors/summary?from=2025-01-01&to=2025-12-31` - Resumo de erros agregados por tipo
- `GET /model/info` - Informações do modelo atual

## 🖥️ UI Streamlit

### Iniciar UI

```bash
# UI incremental (com filtros de data, requer API)
make ui

# Acesse: http://localhost:8501
```

**Nota**: A UI incremental substitui a UI básica e requer que a API esteja rodando (`make api-start`).

### Funcionalidades

**UI Incremental** (`src/ui/app_incremental.py`):
- Filtros de data (from/to)
- Modo Atual (modelo atual) vs Snapshot (versão fixa)
- Visualização de predições e métricas
- Visualização de erros e análise de falhas
- Execução de ETL incremental
- Treino de modelo
- Backfill
- Integração com API REST
- Geração de predições em lote

## 📁 Estrutura do Projeto

```
pipeline-optimizer/
├── src/
│   ├── cli/              # Interface de linha de comando
│   │   ├── fetch.py      # Coleta dados do GitLab
│   │   ├── normalize.py  # Normaliza dados
│   │   ├── analyze.py    # Análise estatística
│   │   ├── recommend.py  # Gera recomendações
│   │   └── etl_incremental.py  # ETL incremental
│   ├── etl/              # ETL incremental
│   │   └── incremental.py
│   ├── ml/               # Machine Learning
│   │   ├── registry.py   # Model Registry
│   │   ├── train.py      # Treino de modelo
│   │   └── backfill.py   # Backfill
│   ├── api/              # API REST
│   │   └── app.py        # FastAPI
│   ├── ui/               # Interface web
│   │   └── app_incremental.py  # UI incremental
│   ├── strategies/       # Algoritmos de recomendação
│   │   └── intelligent_strategy.py
│   └── utils/            # Utilitários
│       ├── dashboard.py  # Geração de dashboard
│       └── synthetic_data.py
├── sql/
│   └── migrations/       # Migrations do banco
│       └── 001_initial_schema.sql
├── models/                # Modelos treinados
│   ├── model_v{N}.pkl
│   ├── transformers/
│   └── schemas/
├── dados/
│   ├── raw/              # Dados brutos (append-only)
│   └── processed/        # Dados processados
├── docker-compose.yml    # Configuração Docker
├── Dockerfile            # Imagem Docker
├── Makefile             # Comandos simplificados
└── requirements.txt     # Dependências Python
```

## ⚙️ Configuração

### Variáveis de Ambiente

```bash
# Obrigatórias
export PROJECT_ID=26454237
export TOKEN=seu_token_gitlab

# Opcionais
export GITLAB_API=https://gitlab.com/api/v4
export MAX_PIPELINES=100
export DB_NAME=pipeline_optimizer
export DB_USER=postgres
export DB_PASS=postgres
export DB_HOST=localhost
export DB_PORT=5432
export REPROCESS_DAYS=3  # Dias para reprocessar na janela deslizante
```

### Configuração do Banco de Dados

O sistema usa PostgreSQL e cria automaticamente o banco e as tabelas na primeira execução via `make db-setup`. As migrations estão em `sql/migrations/001_initial_schema.sql`.

## 🧪 Testes

```bash
# Testes ETL
pytest tests/test_incremental_etl.py -v

# Testes API
pytest tests/test_infer_api.py -v
```

## 🔍 Análise de Erros

A API fornece endpoints específicos para análise de erros:

### Listar Erros

```bash
# Via API
curl "http://localhost:8000/errors?from=2025-01-01&to=2025-12-31&limit=100"

# Via UI
# Acesse a aba "Análise de Erros" na interface
```

### Resumo de Erros

```bash
# Via API
curl "http://localhost:8000/errors/summary?from=2025-01-01&to=2025-12-31"
```

Os erros incluem:
- Job ID e Pipeline ID
- Nome do job e stage
- Motivo da falha (`failure_reason`)
- Contagem de retries
- URLs para visualização no GitLab
- Timestamps de criação e finalização

## 📚 Documentação Adicional

- `VERIFICACAO_FORMULAS.md` - Verificação de fórmulas e cálculos do sistema
- `COMO_USAR_IMAGEM_DOCKER_HUB.md` - Guia completo para usar a imagem do Docker Hub

## 🎯 Casos de Uso

### 1. Análise Completa (Primeira Execução)

```bash
export PROJECT_ID=26454237
export TOKEN=seu_token
make processar
```

### 2. Análise Rápida (Teste)

```bash
make processar-rapido  # Apenas 100 pipelines
```

### 3. Demo com Dados Sintéticos

```bash
make processar-sintetico  # Não precisa de credenciais GitLab
```

### 4. Processamento Incremental (Diário)

```bash
# Primeira vez: coleta completa
make processar

# Próximas vezes: apenas novos dados
make processar  # Detecta automaticamente novos dados via watermark
```

### 5. Gerar Predições em Lote

```bash
# Via API
curl -X POST "http://localhost:8000/predictions/generate"

# Via UI
# Acesse a aba "Predições" e clique em "Gerar Predições"
```

## 🔍 Resultados

Após executar o pipeline, os resultados estarão em:

- `dados/processed/{PROJECT_ID}/RELATORIO_FINAL.html` - Dashboard HTML completo
- `dados/processed/{PROJECT_ID}/recomendacoes_ia_inteligente.csv` - Recomendações
- `dados/processed/{PROJECT_ID}/figuras/` - Gráficos e visualizações

### Acesso via API e UI

Os resultados também podem ser acessados via:
- **API REST**: `http://localhost:8000/docs` - Documentação interativa Swagger
- **UI Streamlit**: `http://localhost:8501` - Interface web completa

## 🛠️ Troubleshooting

### Erro de Permissão ao Iniciar API

Se você encontrar o erro:
```
Error response from daemon: error while creating mount source path '/path/to/models': chown /path/to/models: permission denied
```

**Solução:**

```bash
# Crie os diretórios manualmente com as permissões corretas
mkdir -p models/transformers models/schemas
mkdir -p dados/raw dados/processed
chmod -R 755 models dados

# Ou use o comando do Makefile
make setup-dirs

# Depois tente novamente
make api-start
```

### Porta 8501 já está em uso

Se você encontrar o erro:
```
Bind for 0.0.0.0:8501 failed: port is already allocated
```

**Soluções:**

1. **Usar porta alternativa automaticamente:**
   ```bash
   # O Makefile agora detecta automaticamente e usa porta 8502 se 8501 estiver ocupada
   make up
   ```

2. **Especificar porta manualmente:**
   ```bash
   export STREAMLIT_PORT=8502
   make up
   ```

3. **Parar o processo que está usando a porta:**
   ```bash
   # Ver qual processo está usando a porta
   lsof -i :8501
   
   # Parar o processo (substitua PID pelo número do processo)
   kill -9 <PID>
   ```

### Problemas com Docker no macOS

No macOS, o Docker Desktop pode ter problemas com permissões de volumes. Se o problema persistir:

1. Certifique-se de que os diretórios existem antes de iniciar os serviços
2. Verifique as configurações de compartilhamento de arquivos no Docker Desktop
3. Tente reiniciar o Docker Desktop

## 🤝 Contribuindo

Este é um projeto de TCC. Para uso interno ou contribuições, consulte a documentação adicional.

## 📄 Licença

Projeto acadêmico - TCC.

---

**Pipeline Optimizer** - Otimize seus pipelines CI/CD com IA! 🚀

## 📝 Notas de Versão

### Funcionalidades Principais

- ✅ Processamento incremental com watermark pattern
- ✅ Model Registry com versionamento completo
- ✅ Feature Store (offline/online)
- ✅ API REST completa com documentação Swagger
- ✅ UI Streamlit interativa
- ✅ Análise de erros detalhada
- ✅ Geração de predições em lote
- ✅ Suporte a Docker e Docker Hub