.PHONY: help processar processar-rapido processar-sintetico build up down api-start api-stop api-logs ui ui-incremental clean export-db import-db dist docker-build docker-push docker-pull

# ════════════════════════════════════════════════════════════════════
#                       CONFIGURAÇÃO DOCKER HUB
# ════════════════════════════════════════════════════════════════════

DOCKER_USER ?= seu-usuario
IMAGE_NAME = pipeline-optimizer
VERSION ?= latest

# ════════════════════════════════════════════════════════════════════
#                       MAKEFILE SIMPLIFICADO
# ════════════════════════════════════════════════════════════════════

help: ## 📚 Mostra esta ajuda
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "                    COMANDOS DISPONÍVEIS"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "🔄 PROCESSAMENTO:"
	@echo ""
	@echo "  make processar          - Pipeline completo (dados reais, todos)"
	@echo "  make processar-rapido   - Pipeline rápido (100 pipelines)"
	@echo "  make processar-sintetico - Pipeline com dados sintéticos (demo)"
	@echo ""
	@echo "🔧 SETUP:"
	@echo ""
	@echo "  make build             - Constrói imagem Docker"
	@echo "  make up                - Sobe tudo (banco + API + UI incremental)"
	@echo "  make down              - Para tudo"
	@echo ""
	@echo "🚀 API:"
	@echo ""
	@echo "  make api-start         - Inicia API FastAPI (http://localhost:8000)"
	@echo "  make api-stop          - Para API FastAPI"
	@echo "  make api-logs          - Mostra logs da API"
	@echo ""
	@echo "🧹 LIMPEZA:"
	@echo ""
	@echo "  make clean             - Remove containers e volumes Docker"
	@echo ""
	@echo "📦 DISTRIBUIÇÃO:"
	@echo ""
	@echo "  make export-db         - Exporta banco de dados para backup"
	@echo "  make import-db FILE=   - Importa banco de dados (ex: FILE=backup.sql.gz)"
	@echo "  make dist              - Cria pacote completo (banco + modelos + código)"
	@echo ""
	@echo "🐳 DOCKER HUB:"
	@echo ""
	@echo "  make docker-build          - Build da imagem Docker"
	@echo "  make docker-push          - Push para Docker Hub"
	@echo "  make docker-pull           - Pull da imagem do Docker Hub"
	@echo "  make docker-build-with-data - Build com dados do banco"
	@echo "  make docker-push-with-data  - Push imagem com dados"
	@echo ""
	@echo "   Configure: export DOCKER_USER=seu-usuario"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "💡 Variáveis de ambiente necessárias:"
	@echo ""
	@echo "  export PROJECT_ID=26454237"
	@echo "  export TOKEN=seu_token"
	@echo ""
	@echo "💡 Variáveis opcionais:"
	@echo ""
	@echo "  export MAX_PIPELINES=100        # Limite de pipelines"
	@echo "  export DB_NAME=pipeline_optimizer  # Nome do banco"
	@echo "  export DB_USER=postgres          # Usuário do banco"
	@echo "  export DB_PASS=postgres         # Senha do banco"
	@echo ""

# ════════════════════════════════════════════════════════════════════
#                     🔄 PROCESSAMENTO
# ════════════════════════════════════════════════════════════════════

processar: check-env setup-dirs db-setup ## 🔄 Pipeline completo (dados reais, todos os pipelines)
	@echo "════════════════════════════════════════════════════════════════"
	@echo "         🔄 PIPELINE COMPLETO - DADOS REAIS"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@$(MAKE) fetch-incremental
	@echo ""
	@$(MAKE) etl-incremental
	@echo ""
	@$(MAKE) normalize
	@echo ""
	@$(MAKE) analyze
	@echo ""
	@$(MAKE) rec
	@echo ""
	@$(MAKE) dashboard
	@echo ""
	@echo "✅ Pipeline completo concluído!"
	@echo ""
	@echo "📄 Resultados em: dados/processed/{PROJECT_ID}/"

processar-rapido: check-env setup-dirs db-setup ## 🔄 Pipeline rápido (100 pipelines)
	@echo "════════════════════════════════════════════════════════════════"
	@echo "         ⚡ PIPELINE RÁPIDO - 100 PIPELINES"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@docker-compose run --rm -e MAX_PIPELINES=100 pipeline-optimizer-scripts python src/cli/fetch.py --incremental
	@echo ""
	@$(MAKE) etl-incremental
	@echo ""
	@$(MAKE) normalize
	@echo ""
	@$(MAKE) analyze
	@echo ""
	@$(MAKE) rec
	@echo ""
	@$(MAKE) dashboard
	@echo ""
	@echo "✅ Pipeline rápido concluído!"

processar-sintetico: setup-dirs db-setup ## 🔄 Pipeline com dados sintéticos (demo)
	@echo "════════════════════════════════════════════════════════════════"
	@echo "         🎯 PIPELINE DEMO - DADOS SINTÉTICOS"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@docker-compose run --rm pipeline-optimizer-scripts python src/utils/synthetic_data.py
	@echo ""
	@$(MAKE) normalize
	@echo ""
	@$(MAKE) analyze
	@echo ""
	@$(MAKE) rec
	@echo ""
	@$(MAKE) dashboard
	@echo ""
	@echo "✅ Pipeline sintético concluído!"

# ════════════════════════════════════════════════════════════════════
#                     🔧 SETUP
# ════════════════════════════════════════════════════════════════════

build: ## 🔧 Constrói imagem Docker
	@echo "🔧 Construindo imagem Docker..."
	@docker-compose build
	@echo "✅ Imagem construída!"

up: build db-setup api-start ## 🚀 Sobe tudo (banco + API + UI incremental)
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "         🚀 INICIANDO TODOS OS SERVIÇOS"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "✅ Banco PostgreSQL: rodando"
	@echo "✅ API FastAPI: rodando em http://localhost:8000"
	@echo ""
	@echo "🖥️  Iniciando UI Incremental..."
	@STREAMLIT_PORT=$${STREAMLIT_PORT:-8501}; \
	if lsof -Pi :$$STREAMLIT_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then \
		echo "⚠️  Porta $$STREAMLIT_PORT já está em uso. Tentando porta alternativa..."; \
		STREAMLIT_PORT=8502; \
		if lsof -Pi :$$STREAMLIT_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then \
			echo "❌ Portas 8501 e 8502 estão em uso. Pare o processo ou use: export STREAMLIT_PORT=8503"; \
			exit 1; \
		fi; \
	fi; \
	echo "   Acesse: http://localhost:$$STREAMLIT_PORT"; \
	echo ""; \
	docker-compose run --rm -p $$STREAMLIT_PORT:8501 pipeline-optimizer-scripts streamlit run src/ui/app_incremental.py --server.address 0.0.0.0 --server.port 8501

down: ## 🚀 Para todos os serviços
	@echo "🛑 Parando todos os serviços..."
	@docker-compose stop api postgres
	@echo "✅ Todos os serviços parados!"

setup-dirs: ## 🔧 Cria diretórios necessários
	@mkdir -p dados/raw dados/processed models/transformers models/schemas
	@chmod -R 755 dados models 2>/dev/null || true

check-env: ## 🔧 Verifica variáveis de ambiente (PROJECT_ID, TOKEN)
	@if [ -z "$$PROJECT_ID" ]; then \
		echo "❌ PROJECT_ID não definido"; \
		echo "   Execute: export PROJECT_ID=seu_project_id"; \
		exit 1; \
	fi
	@if [ -z "$$TOKEN" ]; then \
		echo "❌ TOKEN não definido"; \
		echo "   Execute: export TOKEN=seu_token"; \
		exit 1; \
	fi

db-setup: ## 🔧 Cria banco e executa migrations
	@echo "🗄️  Configurando banco de dados PostgreSQL..."
	@docker-compose up -d postgres
	@echo "⏳ Aguardando PostgreSQL ficar pronto..."
	@sleep 5
	@echo "📝 Executando migrations..."
	@docker-compose exec -T postgres psql -U $$(echo $${DB_USER:-postgres}) -d $$(echo $${DB_NAME:-pipeline_optimizer}) -f /docker-entrypoint-initdb.d/001_initial_schema.sql 2>/dev/null || \
		docker-compose exec -T postgres psql -U $$(echo $${DB_USER:-postgres}) -d $$(echo $${DB_NAME:-pipeline_optimizer}) < /docker-entrypoint-initdb.d/001_initial_schema.sql || \
		echo "⚠️  Migration pode já ter sido executada. Continuando..."
	@echo "✅ Banco configurado!"

# ════════════════════════════════════════════════════════════════════
#                     📊 ETAPAS INDIVIDUAIS (internas)
# ════════════════════════════════════════════════════════════════════

fetch-incremental: check-env
	@echo "📥 Coletando dados do GitLab (incremental)..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/cli/fetch.py --incremental

etl-incremental: check-env
	@echo "🔄 Executando ETL Incremental..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/cli/etl_incremental.py --reprocess-days $$(echo $${REPROCESS_DAYS:-3})

normalize:
	@echo "📊 Normalizando dados..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/cli/normalize.py

analyze: normalize
	@echo "📈 Analisando dados..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/cli/analyze.py

rec:
	@echo "🤖 Gerando recomendações..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/cli/recommend.py

dashboard:
	@echo "🌐 Gerando dashboard..."
	@docker-compose run --rm pipeline-optimizer-scripts python src/utils/dashboard.py

# ════════════════════════════════════════════════════════════════════
#                     🚀 API
# ════════════════════════════════════════════════════════════════════

api-start: db-setup setup-dirs ## 🚀 Inicia API FastAPI (http://localhost:8000)
	@echo "🚀 Iniciando API FastAPI em http://localhost:8000"
	@docker-compose up -d api
	@echo "✅ API rodando! Acesse: http://localhost:8000/docs"

api-stop: ## 🚀 Para API FastAPI
	@docker-compose stop api
	@echo "✅ API parada"

api-logs: ## 🚀 Mostra logs da API
	@docker-compose logs -f api

# ════════════════════════════════════════════════════════════════════
#                     🧹 LIMPEZA
# ════════════════════════════════════════════════════════════════════

clean: ## 🧹 Remove containers e volumes Docker
	@echo "🧹 Removendo containers e volumes..."
	@docker-compose down -v
	@echo "✅ Limpeza concluída!"

export-db: ## 📦 Exporta banco de dados para distribuição
	@echo "📦 Exportando banco de dados..."
	@chmod +x scripts/export_database.sh
	@./scripts/export_database.sh database_backup_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "✅ Banco exportado!"

import-db: ## 📥 Importa banco de dados (use: make import-db FILE=backup.sql.gz)
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Especifique o arquivo: make import-db FILE=database_backup.sql.gz"; \
		exit 1; \
	fi
	@echo "📥 Importando banco de dados..."
	@chmod +x scripts/import_database.sh
	@./scripts/import_database.sh $(FILE)
	@echo "✅ Banco importado!"

dist: export-db ## 📦 Cria pacote completo para distribuição (inclui dados e modelos)
	@echo "📦 Criando pacote de distribuição..."
	@mkdir -p pipeline-optimizer-dist
	@echo "   📁 Copiando código e configurações..."
	@cp -r src sql Dockerfile docker-compose.dist.yml requirements.txt pipeline-optimizer-dist/ 2>/dev/null || true
	@cp docker-compose.dist.yml pipeline-optimizer-dist/docker-compose.yml 2>/dev/null || true
	@echo "   📁 Copiando modelos..."
	@cp -r models pipeline-optimizer-dist/ 2>/dev/null || true
	@echo "   📁 Copiando dados processados..."
	@cp -r dados pipeline-optimizer-dist/ 2>/dev/null || true
	@LATEST_BACKUP=$$(ls -t database_backup_*.sql.gz 2>/dev/null | head -1); \
	if [ -n "$$LATEST_BACKUP" ]; then \
		echo "   📁 Copiando backup do banco..."; \
		cp "$$LATEST_BACKUP" pipeline-optimizer-dist/database_backup.sql.gz; \
	fi
	@cat > pipeline-optimizer-dist/setup.sh << 'EOF' \
	#!/bin/bash\n\
	set -e\n\
	echo "🚀 Pipeline Optimizer - Setup"\n\
	echo ""\n\
	docker-compose up -d postgres\n\
	echo "⏳ Aguardando PostgreSQL..."\n\
	sleep 5\n\
	if [ -f "database_backup.sql.gz" ]; then\n\
		echo "📥 Importando banco de dados..."\n\
		gunzip -c database_backup.sql.gz | docker-compose exec -T postgres psql -U postgres -d pipeline_optimizer\n\
		echo "✅ Banco importado!"\n\
	else\n\
		echo "⚠️  database_backup.sql.gz não encontrado. Criando banco vazio..."\n\
		docker-compose exec -T postgres psql -U postgres -d pipeline_optimizer -f /docker-entrypoint-initdb.d/001_initial_schema.sql\n\
	fi\n\
	echo "🚀 Iniciando API..."\n\
	docker-compose up -d api\n\
	echo ""\n\
	echo "✅ Setup concluído!"\n\
	echo ""\n\
	echo "📊 Serviços disponíveis:"\n\
	echo "   - API: http://localhost:8000"\n\
	echo "   - API Docs: http://localhost:8000/docs"\n\
	echo "   - Health: http://localhost:8000/healthz"\n\
	echo ""\n\
	echo "🖥️  Para iniciar a UI:"\n\
	echo "   docker-compose run --rm -p 8501:8501 pipeline-optimizer-scripts streamlit run src/ui/app_incremental.py --server.address 0.0.0.0 --server.port 8501"\n\
	EOF
	@chmod +x pipeline-optimizer-dist/setup.sh
	@cat > pipeline-optimizer-dist/Makefile << 'EOF' \
	.PHONY: help setup ui fetch etl train api-start api-stop\n\
	\n\
	help: ## 📚 Mostra esta ajuda\n\
		@echo ""\n\
		@echo "════════════════════════════════════════════════════════════════"\n\
		@echo "                    COMANDOS DISPONÍVEIS"\n\
		@echo "════════════════════════════════════════════════════════════════"\n\
		@echo ""\n\
		@echo "🚀 SETUP:"\n\
		@echo "  make setup          - Configura banco e inicia serviços"\n\
		@echo "  make ui             - Inicia UI Streamlit (http://localhost:8501)"\n\
		@echo ""\n\
		@echo "📥 DADOS:"\n\
		@echo "  make fetch          - Coleta novos dados do GitLab"\n\
		@echo "  make etl            - Processa dados (ETL incremental)"\n\
		@echo ""\n\
		@echo "⚙️  MODELO:"\n\
		@echo "  make train          - Treina novo modelo com dados disponíveis"\n\
		@echo ""\n\
		@echo "🚀 API:"\n\
		@echo "  make api-start      - Inicia API (http://localhost:8000)"\n\
		@echo "  make api-stop       - Para API"\n\
		@echo ""\n\
		@echo "💡 Configure antes de usar:"\n\
		@echo "  export PROJECT_ID=seu_project_id"\n\
		@echo "  export TOKEN=seu_token"\n\
		@echo ""\n\
	\n\
	setup: ## 🚀 Setup inicial\n\
		@./setup.sh\n\
	\n\
	ui: ## 🖥️  Inicia UI Streamlit\n\
		@docker-compose run --rm -p 8501:8501 pipeline-optimizer-scripts \\\n\
			streamlit run src/ui/app_incremental.py --server.address 0.0.0.0 --server.port 8501\n\
	\n\
	fetch: ## 📥 Coleta dados do GitLab\n\
		@if [ -z "$$PROJECT_ID" ] || [ -z "$$TOKEN" ]; then \\\n\
			echo "❌ Configure PROJECT_ID e TOKEN primeiro"; \\\n\
			exit 1; \\\n\
		fi\n\
		@echo "📥 Coletando dados do GitLab..."\n\
		@docker-compose run --rm -e PROJECT_ID=$$PROJECT_ID -e TOKEN=$$TOKEN \\\n\
			pipeline-optimizer-scripts python src/cli/fetch.py --incremental\n\
	\n\
	etl: ## 🔄 Processa dados (ETL)\n\
		@if [ -z "$$PROJECT_ID" ]; then \\\n\
			echo "❌ Configure PROJECT_ID primeiro"; \\\n\
			exit 1; \\\n\
		fi\n\
		@echo "🔄 Executando ETL incremental..."\n\
		@docker-compose run --rm -e PROJECT_ID=$$PROJECT_ID \\\n\
			pipeline-optimizer-scripts python src/cli/etl_incremental.py --reprocess-days $$(echo $${REPROCESS_DAYS:-3})\n\
	\n\
	train: ## ⚙️  Treina novo modelo\n\
		@if [ -z "$$PROJECT_ID" ]; then \\\n\
			echo "❌ Configure PROJECT_ID primeiro"; \\\n\
			exit 1; \\\n\
		fi\n\
		@echo "⚙️  Treinando modelo..."\n\
		@docker-compose run --rm -e PROJECT_ID=$$PROJECT_ID \\\n\
			pipeline-optimizer-scripts python src/ml/train.py --all\n\
		@echo "✅ Modelo treinado! Reinicie a API: make api-stop && make api-start"\n\
	\n\
	api-start: ## 🚀 Inicia API\n\
		@docker-compose up -d api\n\
		@echo "✅ API rodando em http://localhost:8000"\n\
		@echo "📚 Docs: http://localhost:8000/docs"\n\
	\n\
	api-stop: ## 🛑 Para API\n\
		@docker-compose stop api\n\
		@echo "✅ API parada"\n\
	EOF
	@cat > pipeline-optimizer-dist/README.md << 'EOF' \
	# Pipeline Optimizer - Distribuição Completa\n\
	\n\
	Este pacote inclui:\n\
	- ✅ Código fonte completo\n\
	- ✅ Modelos pré-treinados (v2-v6)\n\
	- ✅ Dados processados\n\
	- ✅ Banco de dados pré-populado\n\
	- ✅ Tudo configurado e pronto para uso\n\
	\n\
	## 🚀 Início Rápido\n\
	\n\
	### Pré-requisitos\n\
	\n\
	- Docker e Docker Compose instalados\n\
	\n\
	### 1. Setup Inicial\n\
	\n\
	\`\`\`bash\n\
	# Execute o script de setup (importa banco e inicia API)\n\
	./setup.sh\n\
	\`\`\`\n\
	\n\
	### 2. Iniciar UI\n\
	\n\
	\`\`\`bash\n\
	make ui\n\
	# Ou manualmente:\n\
	# docker-compose run --rm -p 8501:8501 pipeline-optimizer-scripts \\\n\
	#   streamlit run src/ui/app_incremental.py --server.address 0.0.0.0 --server.port 8501\n\
	\`\`\`\n\
	\n\
	Acesse: **http://localhost:8501**\n\
	\n\
	## 📥 Adicionar Novos Dados\n\
	\n\
	### Opção 1: Via UI (Recomendado)\n\
	\n\
	1. Acesse a UI: http://localhost:8501\n\
	2. Configure `PROJECT_ID` e `TOKEN` no sidebar\n\
	3. Vá na aba "📥 Obter Dados"\n\
	4. Clique em "Buscar Dados"\n\
	\n\
	### Opção 2: Via Makefile\n\
	\n\
	\`\`\`bash\n\
	# Configure credenciais\n\
	export PROJECT_ID="seu_project_id"\n\
	export TOKEN="seu_token"\n\
	\n\
	# Coletar dados\n\
	make fetch\n\
	\n\
	# Processar dados (ETL)\n\
	make etl\n\
	\`\`\`\n\
	\n\
	## ⚙️ Treinar Novo Modelo\n\
	\n\
	### Via UI\n\
	\n\
	1. Acesse a UI: http://localhost:8501\n\
	2. Vá na aba "⚙️ Treino"\n\
	3. Configure parâmetros\n\
	4. Clique em "Treinar Modelo"\n\
	\n\
	### Via Makefile\n\
	\n\
	\`\`\`bash\n\
	export PROJECT_ID="seu_project_id"\n\
	make train\n\
	\`\`\`\n\
	\n\
	## 📊 Comandos Disponíveis\n\
	\n\
	\`\`\`bash\n\
	make help          # Ver todos os comandos\n\
	make setup         # Setup inicial\n\
	make ui            # Iniciar UI\n\
	make fetch         # Coletar dados do GitLab\n\
	make etl           # Processar dados (ETL)\n\
	make train         # Treinar modelo\n\
	make api-start     # Iniciar API\n\
	make api-stop      # Parar API\n\
	\`\`\`\n\
	\n\
	## 📊 O que está incluído\n\
	\n\
	### Modelos Treinados\n\
	- **v6** (atual em produção)\n\
	- v2-v5 (histórico)\n\
	\n\
	### Dados Processados\n\
	- Métricas diárias\n\
	- Features offline/online\n\
	- Predições geradas\n\
	- Relatórios e gráficos\n\
	\n\
	### Banco de Dados\n\
	- Dados raw (pipelines e jobs)\n\
	- Métricas diárias processadas\n\
	- Features offline/online\n\
	- Predições geradas\n\
	- Model registry\n\
	\n\
	## 🔧 Configuração\n\
	\n\
	Para usar com seu próprio projeto GitLab:\n\
	\n\
	\`\`\`bash\n\
	export PROJECT_ID="seu_project_id"\n\
	export TOKEN="seu_token"\n\
	export GITLAB_API="https://gitlab.com/api/v4"\n\
	\`\`\`\n\
	\n\
	## 🆘 Troubleshooting\n\
	\n\
	### Banco não importa\n\
	\`\`\`bash\n\
	docker-compose logs postgres\n\
	gunzip -c database_backup.sql.gz | docker-compose exec -T postgres psql -U postgres -d pipeline_optimizer\n\
	\`\`\`\n\
	\n\
	### API não inicia\n\
	\`\`\`bash\n\
	docker-compose logs api\n\
	docker-compose restart api\n\
	\`\`\`\n\
	\n\
	### Erro ao coletar dados\n\
	- Verifique se `PROJECT_ID` e `TOKEN` estão configurados\n\
	- Verifique se o token tem permissão `read_api`\n\
	EOF
	@tar -czf pipeline-optimizer-completo-v1.0.0.tar.gz \
		--exclude='.git' \
		--exclude='*.pyc' \
		--exclude='__pycache__' \
		--exclude='dados/raw' \
		pipeline-optimizer-dist/ 2>/dev/null || true
	@echo ""
	@echo "✅ Pacote criado: pipeline-optimizer-completo-v1.0.0.tar.gz"
	@echo "   📦 Inclui: código + modelos + dados processados + banco"

# ════════════════════════════════════════════════════════════════════
#                     🐳 DOCKER HUB
# ════════════════════════════════════════════════════════════════════

docker-build: ## 🐳 Build da imagem Docker
	@echo "🐳 Construindo imagem Docker..."
	@echo "   Usuário: $(DOCKER_USER)"
	@echo "   Imagem: $(IMAGE_NAME)"
	@echo "   Versão: $(VERSION)"
	@docker build -t $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION) .
	@if [ "$(VERSION)" != "latest" ]; then \
		echo "   Criando tag 'latest'..."; \
		docker tag $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION) $(DOCKER_USER)/$(IMAGE_NAME):latest; \
	fi
	@echo "✅ Imagem construída: $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)"

docker-push: docker-build ## 🐳 Push para Docker Hub
	@echo "🐳 Enviando imagem para Docker Hub..."
	@echo "   Usuário: $(DOCKER_USER)"
	@echo "   Imagem: $(IMAGE_NAME)"
	@echo "   Versão: $(VERSION)"
	@docker push $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)
	@if [ "$(VERSION)" != "latest" ]; then \
		echo "   Enviando tag 'latest'..."; \
		docker push $(DOCKER_USER)/$(IMAGE_NAME):latest; \
	fi
	@echo "✅ Imagem enviada para Docker Hub!"
	@echo "   Pull com: docker pull $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)"

docker-pull: ## 🐳 Pull da imagem do Docker Hub
	@echo "🐳 Baixando imagem do Docker Hub..."
	@echo "   Usuário: $(DOCKER_USER)"
	@echo "   Imagem: $(IMAGE_NAME)"
	@echo "   Versão: $(VERSION)"
	@docker pull $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)
	@echo "✅ Imagem baixada: $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)"

docker-build-with-data: export-db ## 🐳 Build da imagem Docker com dados do banco
	@echo "🐳 Construindo imagem Docker com dados do banco..."
	@echo "   Usuário: $(DOCKER_USER)"
	@echo "   Imagem: $(IMAGE_NAME)"
	@echo "   Versão: $(VERSION)"
	@LATEST_BACKUP=$$(ls -t database_backup_*.sql.gz 2>/dev/null | head -1); \
	if [ -z "$$LATEST_BACKUP" ]; then \
		echo "❌ Nenhum backup do banco encontrado. Execute 'make export-db' primeiro."; \
		exit 1; \
	fi; \
	echo "   Usando backup: $$LATEST_BACKUP"; \
	cp "$$LATEST_BACKUP" database_backup.sql.gz; \
	echo "   Criando .dockerignore temporário (incluindo dados e models)..."; \
	cp .dockerignore .dockerignore.bak 2>/dev/null || touch .dockerignore.bak; \
	sed '/^dados\//d; /^models\//d' .dockerignore.bak > .dockerignore.tmp 2>/dev/null || echo "" > .dockerignore.tmp; \
	mv .dockerignore.tmp .dockerignore; \
	docker build -f Dockerfile.with-data -t $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)-with-data .; \
	BUILD_EXIT=$$?; \
	rm -f database_backup.sql.gz; \
	mv .dockerignore.bak .dockerignore 2>/dev/null || rm -f .dockerignore; \
	if [ $$BUILD_EXIT -ne 0 ]; then exit $$BUILD_EXIT; fi; \
	if [ "$(VERSION)" != "latest" ]; then \
		echo "   Criando tag 'latest-with-data'..."; \
		docker tag $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)-with-data $(DOCKER_USER)/$(IMAGE_NAME):latest-with-data; \
	fi; \
	echo "✅ Imagem construída: $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)-with-data"

docker-push-with-data: docker-build-with-data ## 🐳 Push da imagem com dados para Docker Hub
	@echo "🐳 Enviando imagem com dados para Docker Hub..."
	@echo "   Usuário: $(DOCKER_USER)"
	@echo "   Imagem: $(IMAGE_NAME)"
	@echo "   Versão: $(VERSION)-with-data"
	@docker push $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)-with-data
	@if [ "$(VERSION)" != "latest" ]; then \
		echo "   Enviando tag 'latest-with-data'..."; \
		docker push $(DOCKER_USER)/$(IMAGE_NAME):latest-with-data; \
	fi
	@echo "✅ Imagem com dados enviada para Docker Hub!"
	@echo "   Pull com: docker pull $(DOCKER_USER)/$(IMAGE_NAME):$(VERSION)-with-data"
