"""
Streamlit UI - Interface Reorganizada

Estrutura:
- Sidebar: Configurações (banco, token, backend, pipeline URL)
- Tabs principais: Obter Dados, Processar Dados, Treino, Métricas
"""

import os
import sys
import subprocess
import json
import traceback
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional
import streamlit as st
import requests
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]

# Configuração da API
# Detecta se está rodando no Docker e usa o nome do serviço
# Quando roda no Docker, usa o nome do serviço 'api'
# Quando roda localmente, usa localhost
def get_api_url():
    """Retorna a URL da API baseada no ambiente"""
    api_url_env = os.getenv("API_BASE_URL")
    if api_url_env:
        return api_url_env
    
    # Se está no Docker (detecta pela variável DB_HOST ou pela existência de /app)
    if os.path.exists("/app") or os.getenv("DB_HOST") == "postgres":
        return "http://api:8000"
    
    return "http://localhost:8000"

API_BASE_URL = get_api_url()


def run_cmd(cmd: list[str], extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    if extra_env:
        env.update(extra_env)
    with subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as p:
        for line in p.stdout:  # type: ignore[attr-defined]
            st.write(line.rstrip())
        return p.wait()


def run_cmd_with_progress(cmd: list[str], extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["DASHBOARD_NO_OPEN"] = "1"
    env["MPLBACKEND"] = "Agg"
    if extra_env:
        env.update(extra_env)

    progress = st.progress(0)
    logs_area = st.empty()
    current_pct = 0
    line_count = 0
    buffer = []

    def update_progress_from_line(line: str):
        nonlocal current_pct
        if "✅" in line or "concluído" in line.lower():
            current_pct = min(current_pct + 10, 95)
            progress.progress(current_pct)

    with subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as p:
        for raw in p.stdout:  # type: ignore[attr-defined]
            line = raw.rstrip()
            buffer.append(line)
            if len(buffer) > 100:
                buffer.pop(0)
            logs_area.code("\n".join(buffer), language="bash")
            update_progress_from_line(line)
            line_count += 1
            if line_count % 25 == 0 and current_pct < 95:
                current_pct += 1
                progress.progress(min(current_pct, 100))
        ret = p.wait()
    if ret == 0:
        progress.progress(100)
    return ret


st.set_page_config(page_title="Pipeline Optimizer", page_icon="📊", layout="wide")
st.title("📊 Pipeline Optimizer")

# PROJECT_ID no cabeçalho
col_project1, col_project2 = st.columns([1, 4])
with col_project1:
    st.write("**PROJECT_ID:**")
with col_project2:
    project_id = st.text_input(
        "PROJECT_ID",
        value=st.session_state.get('project_id', os.getenv("PROJECT_ID", "")),
        key="project_id_header",
        label_visibility="collapsed",
        placeholder="Digite o PROJECT_ID do GitLab"
    )
    if project_id:
        st.session_state['project_id'] = project_id

st.divider()

# ================================================================
# SIDEBAR - Configurações
# ================================================================

with st.sidebar:
    st.header("⚙️ Configurações")
    
    st.subheader("🗄️ Banco de Dados")
    db_host = st.text_input("DB_HOST", value=st.session_state.get('db_host', os.getenv("DB_HOST", "localhost")), key="input_db_host")
    db_port = st.text_input("DB_PORT", value=st.session_state.get('db_port', os.getenv("DB_PORT", "5432")), key="input_db_port")
    db_name = st.text_input("DB_NAME", value=st.session_state.get('db_name', os.getenv("DB_NAME", "pipeline_optimizer")), key="input_db_name")
    db_user = st.text_input("DB_USER", value=st.session_state.get('db_user', os.getenv("DB_USER", "postgres")), key="input_db_user")
    db_pass = st.text_input("DB_PASS", value=st.session_state.get('db_pass', os.getenv("DB_PASS", "postgres")), type="password", key="input_db_pass")
    
    st.divider()
    
    st.subheader("🔐 Autenticação")
    token = st.text_input("TOKEN (GitLab)", value=st.session_state.get('token', os.getenv("TOKEN", "")), type="password", key="input_token")
    
    st.divider()
    
    st.subheader("🔌 Backend")
    api_url = st.text_input("API URL", value=st.session_state.get('api_url', get_api_url()), key="input_api_url", help="Use 'http://api:8000' no Docker ou 'http://localhost:8000' localmente")
    
    st.divider()
    
    st.subheader("🔗 Pipeline")
    gitlab_api = st.text_input("GitLab API URL", value=st.session_state.get('gitlab_api', os.getenv("GITLAB_API", "https://gitlab.com/api/v4")), key="input_gitlab_api")
    
    st.divider()
    
    if st.button("💾 Salvar Configurações", type="primary"):
        st.session_state['db_host'] = db_host
        st.session_state['db_port'] = db_port
        st.session_state['db_name'] = db_name
        st.session_state['db_user'] = db_user
        st.session_state['db_pass'] = db_pass
        st.session_state['token'] = token
        st.session_state['api_url'] = api_url
        st.session_state['gitlab_api'] = gitlab_api
        st.session_state['project_id'] = project_id
        st.success("✅ Configurações salvas!")
        st.rerun()  # Recarrega a página para atualizar os valores dos inputs

# Usa valores da sessão ou sidebar (project_id vem do cabeçalho)
env_vars = {
    "DB_HOST": st.session_state.get('db_host', db_host),
    "DB_PORT": st.session_state.get('db_port', db_port),
    "DB_NAME": st.session_state.get('db_name', db_name),
    "DB_USER": st.session_state.get('db_user', db_user),
    "DB_PASS": st.session_state.get('db_pass', db_pass),
    "TOKEN": st.session_state.get('token', token),
    "GITLAB_API": st.session_state.get('gitlab_api', gitlab_api),
    "PROJECT_ID": st.session_state.get('project_id', project_id or os.getenv("PROJECT_ID", "")),
}

API_BASE_URL = st.session_state.get('api_url', api_url)

# Constrói DATABASE_URL
db_url = f"postgresql://{env_vars['DB_USER']}:{env_vars['DB_PASS']}@{env_vars['DB_HOST']}:{env_vars['DB_PORT']}/{env_vars['DB_NAME']}"
env_vars['DATABASE_URL'] = db_url

# ================================================================
# TABS PRINCIPAIS
# ================================================================

tab1, tab2, tab3, tab4 = st.tabs(["📥 Obter Dados", "🔄 Processar Dados", "⚙️ Treino", "📈 Métricas"])

# TAB 1: Obter Dados
with tab1:
    st.subheader("📥 Obter Dados do GitLab")
    st.caption("Coleta dados do GitLab e armazena no banco de dados")
    
    # Opção: Todos ou Filtrar por data
    filtro_tipo = st.radio(
        "Tipo de coleta:",
        ["Todos os dados", "Filtrar por data"],
        horizontal=True,
        help="Escolha entre coletar todos os dados disponíveis ou filtrar por período"
    )
    
    if filtro_tipo == "Filtrar por data":
        col_date1, col_date2 = st.columns(2)
        
        with col_date1:
            from_date = st.date_input(
                "Data Início",
                value=date.today() - timedelta(days=30),
                help="Data inicial para coleta"
            )
        
        with col_date2:
            to_date = st.date_input(
                "Data Fim",
                value=date.today(),
                help="Data final para coleta"
            )
    else:
        from_date = None
        to_date = None
    
    st.divider()
    
    if st.button("📥 Coletar e Armazenar Dados", type="primary"):
        if not env_vars.get("PROJECT_ID") or not env_vars.get("TOKEN"):
            st.error("❌ PROJECT_ID e TOKEN são obrigatórios! Configure no sidebar.")
        else:
            st.info("🔄 Coletando dados do GitLab...")
            
            # Passo 1: Executa fetch.py (salva JSONs)
            cmd_fetch = [sys.executable, "src/cli/fetch.py"]
            
            # Se escolheu filtrar por data, usa --updated-after
            if filtro_tipo == "Filtrar por data" and from_date:
                updated_after = from_date.isoformat() + "T00:00:00Z"
                cmd_fetch += ["--updated-after", updated_after]
            # Se escolheu "Todos os dados", não passa nenhum parâmetro (coleta tudo)
            # O fetch.py sem parâmetros coleta todos os pipelines disponíveis
            
            code_fetch = run_cmd_with_progress(cmd_fetch, extra_env=env_vars)
            
            if code_fetch == 0:
                st.info("📦 Carregando dados no banco...")
                
                # Passo 2: Carrega JSONs no banco usando ETL
                try:
                    sys.path.insert(0, str(BASE_DIR))
                    from src.etl.incremental import IncrementalETL
                    from src.core.config import Config
                    
                    # Configura PROJECT_ID temporariamente
                    project_id_int = int(env_vars['PROJECT_ID'])
                    os.environ['PROJECT_ID'] = str(project_id_int)
                    Config.PROJECT_ID = project_id_int
                    
                    # Calcula o caminho diretamente (Config.DATA_RAW_DIR pode estar com valor antigo)
                    raw_dir = BASE_DIR / "dados" / "raw" / str(project_id_int)
                    
                    st.write(f"🔍 PROJECT_ID configurado: {project_id_int}")
                    st.write(f"🔍 DATA_RAW_DIR usado: {raw_dir}")
                    
                    # Conecta ao banco
                    etl = IncrementalETL(db_url=db_url)
                    etl.connect()
                    st.write("✅ Conectado ao banco de dados")
                    
                    # Carrega pipelines - usa o caminho calculado diretamente
                    pipelines_file = raw_dir / "pipelines.json"
                    st.write(f"🔍 Procurando arquivo: {pipelines_file}")
                    st.write(f"🔍 Arquivo existe? {pipelines_file.exists()}")
                    
                    if pipelines_file.exists():
                        with open(pipelines_file, 'r') as f:
                            pipelines_data = json.load(f)
                        st.write(f"🔍 Pipelines carregados do JSON: {len(pipelines_data) if pipelines_data else 0}")
                        
                        if pipelines_data:
                            df_pipes = pd.DataFrame(pipelines_data)
                            st.write(f"🔍 DataFrame criado com {len(df_pipes)} linhas")
                            st.write(f"🔍 Colunas: {list(df_pipes.columns)}")
                            
                            # Verifica se tem a coluna 'id'
                            if 'id' in df_pipes.columns:
                                st.write(f"🔍 Primeiro ID: {df_pipes['id'].iloc[0] if len(df_pipes) > 0 else 'N/A'}")
                            
                            etl.append_raw_to_db('pipelines', df_pipes)
                            st.write(f"✅ {len(df_pipes)} pipelines processados")
                        else:
                            st.warning("⚠️ Arquivo pipelines.json está vazio")
                    else:
                        st.error(f"❌ Arquivo não encontrado: {pipelines_file}")
                        # Lista arquivos no diretório
                        if raw_dir.exists():
                            files = list(raw_dir.glob("*"))
                            st.write(f"📁 Arquivos no diretório: {[f.name for f in files]}")
                        else:
                            st.write(f"📁 Diretório não existe: {raw_dir}")
                            # Tenta listar o diretório pai
                            parent_dir = raw_dir.parent
                            if parent_dir.exists():
                                st.write(f"📁 Diretórios em {parent_dir}: {[d.name for d in parent_dir.iterdir() if d.is_dir()]}")
                    
                    # Carrega jobs - usa o caminho calculado diretamente
                    jobs_files = list(raw_dir.glob("jobs_*.json"))
                    st.write(f"🔍 Arquivos de jobs encontrados: {len(jobs_files)}")
                    
                    total_jobs = 0
                    for job_file in jobs_files:
                        with open(job_file, 'r') as f:
                            jobs_data = json.load(f)
                        if jobs_data:
                            df_jobs = pd.DataFrame(jobs_data)
                            etl.append_raw_to_db('jobs', df_jobs)
                            total_jobs += len(df_jobs)
                    
                    if total_jobs > 0:
                        st.write(f"✅ {total_jobs} jobs carregados")
                    
                    etl.close()
                    
                    st.success("✅ Dados coletados e armazenados no banco!")
                    
                    # Mostra resumo
                    try:
                        import psycopg2
                        conn = psycopg2.connect(db_url)
                        with conn.cursor() as cur:
                            cur.execute("SELECT COUNT(*) FROM pipelines_raw WHERE project_id = %s", (project_id_int,))
                            count = cur.fetchone()[0]
                            st.info(f"📊 Total de pipelines no banco: {count}")
                        conn.close()
                    except Exception as e:
                        st.warning(f"⚠️ Não foi possível verificar contagem: {e}")
                        
                except Exception as e:
                    st.error(f"❌ Erro ao carregar no banco: {e}")
                    st.code(traceback.format_exc())
            else:
                st.error(f"❌ Coleta terminou com código {code_fetch}")

# TAB 2: Processar Dados (ETL)
with tab2:
    st.subheader("🔄 Processar Dados (ETL Incremental)")
    st.caption("Executa ETL incremental: calcula métricas e constrói features")
    
    # Opção: Processar tudo ou últimos N dias
    processar_tudo = st.checkbox(
        "Processar todos os dados (sem limite de dias)",
        value=False,
        help="Se marcado, processa todos os dados disponíveis. Se desmarcado, processa apenas os últimos N dias."
    )
    
    if not processar_tudo:
        col_etl1, col_etl2 = st.columns(2)
        
        with col_etl1:
            reprocess_days = st.number_input(
                "Dias para Reprocessar",
                min_value=1,
                max_value=365,
                value=3,
                help="Janela deslizante: reprocessa últimos N dias para corrigir atrasos"
            )
        
        with col_etl2:
            st.write("")  # Espaçamento
    else:
        reprocess_days = None
        st.info("ℹ️ Todos os dados serão processados (pode levar mais tempo)")
    
    if st.button("🔄 Executar ETL Incremental", type="primary"):
        if not env_vars.get("PROJECT_ID"):
            st.error("❌ PROJECT_ID é obrigatório! Configure no sidebar.")
        else:
            st.info("🔄 Executando ETL incremental...")
            
            cmd = [sys.executable, "src/cli/etl_incremental.py"]
            
            if processar_tudo:
                # Processar tudo: usa flag --process-all
                cmd += ["--process-all"]
                st.info("📊 Processando todos os dados disponíveis (pode levar mais tempo)...")
            else:
                cmd += ["--reprocess-days", str(reprocess_days)]
            
            code = run_cmd_with_progress(cmd, extra_env=env_vars)
            
            if code == 0:
                st.success("✅ ETL concluído!")
                
                # Mostra resumo
                try:
                    import psycopg2
                    conn = psycopg2.connect(db_url)
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM metrics_daily WHERE project_id = %s", (env_vars['PROJECT_ID'],))
                        metrics_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM features_online")
                        features_count = cur.fetchone()[0]
                        st.info(f"📊 Métricas diárias: {metrics_count} | Features: {features_count}")
                    conn.close()
                except Exception as e:
                    st.warning(f"⚠️ Não foi possível verificar contagem: {e}")
            else:
                st.error(f"❌ ETL terminou com código {code}")

# TAB 3: Treino
with tab3:
    st.subheader("⚙️ Treinar Modelo")
    st.caption("Treina novo modelo ML com dados históricos")
    
    # Opção: Treinar com todos os dados ou janela específica
    treinar_todos = st.checkbox(
        "Treinar com todos os dados disponíveis (sem limite de janela)",
        value=False,
        help="Se marcado, treina com todos os dados disponíveis. Se desmarcado, usa a janela especificada."
    )
    
    if not treinar_todos:
        col_train1, col_train2 = st.columns(2)
        
        with col_train1:
            window_start = st.date_input(
                "Janela Início",
                value=date.today() - timedelta(days=180),
                help="Data início do período de treino"
            )
        
        with col_train2:
            window_end = st.date_input(
                "Janela Fim",
                value=date.today(),
                help="Data fim do período de treino"
            )
    else:
        window_start = None
        window_end = None
        st.info("ℹ️ Todos os dados disponíveis serão usados para treino (pode levar mais tempo)")
    
    st.divider()
    
    if st.button("🎓 Treinar Modelo", type="primary"):
        if not env_vars.get("PROJECT_ID"):
            st.error("❌ PROJECT_ID é obrigatório! Configure no sidebar.")
        else:
            st.info("🎓 Treinando modelo...")
            
            cmd = [sys.executable, "src/ml/train.py"]
            
            if treinar_todos:
                # Treinar com todos os dados: usa flag --all
                cmd += ["--all"]
                st.info("📊 Treinando com todos os dados disponíveis...")
            else:
                cmd += [
                    "--window-start", window_start.isoformat(),
                    "--window-end", window_end.isoformat()
                ]
            
            code = run_cmd_with_progress(cmd, extra_env=env_vars)
            
            if code == 0:
                st.success("✅ Modelo treinado com sucesso!")
                
                # Mostra versão do modelo atual
                try:
                    import psycopg2
                    conn = psycopg2.connect(db_url)
                    with conn.cursor() as cur:
                        cur.execute("SELECT value FROM kv_config WHERE key = 'MODEL_CURRENT'")
                        row = cur.fetchone()
                        if row:
                            st.info(f"📊 Modelo atual: v{row[0]}")
                    conn.close()
                except Exception as e:
                    st.warning(f"⚠️ Não foi possível verificar versão: {e}")
            else:
                st.error(f"❌ Treino terminou com código {code}")
    
    st.divider()
    
    st.subheader("🔄 Backfill")
    st.caption("Re-scora predições históricas com modelo específico")
    
    col_bf1, col_bf2 = st.columns(2)
    
    with col_bf1:
        model_version = st.number_input(
            "Versão do Modelo",
            min_value=1,
            value=1,
            help="Versão do modelo para backfill"
        )
    
    with col_bf2:
        backfill_days = st.number_input(
            "Dias para Backfill",
            min_value=1,
            max_value=90,
            value=30,
            help="Quantos dias re-scorar"
        )
    
    if st.button("🔄 Executar Backfill"):
        if not env_vars.get("PROJECT_ID"):
            st.error("❌ PROJECT_ID é obrigatório! Configure no sidebar.")
        else:
            st.info("🔄 Executando backfill...")
            
            cmd = [
                sys.executable, "src/ml/backfill.py",
                "--model-version", str(model_version),
                "--days", str(backfill_days)
            ]
            
            code = run_cmd_with_progress(cmd, extra_env=env_vars)
            
            if code == 0:
                st.success("✅ Backfill concluído!")
            else:
                st.error(f"❌ Backfill terminou com código {code}")

# TAB 4: Métricas
with tab4:
    st.subheader("📈 Métricas e Predições")
    st.caption("Visualize métricas diárias e predições do modelo")
    
    # Sub-tabs dentro de Métricas
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📊 Métricas Diárias", "🔮 Predições do Modelo", "❌ Erros das Pipelines"])
    
    # SUB-TAB 1: Métricas Diárias
    with sub_tab1:
        col_metrics1, col_metrics2 = st.columns(2)
        
        with col_metrics1:
            metrics_from = st.date_input(
                "Data Início",
                value=date.today() - timedelta(days=30),
                key="metrics_from",
                help="Data início para visualização"
            )
        
        with col_metrics2:
            metrics_to = st.date_input(
                "Data Fim",
                value=date.today(),
                key="metrics_to",
                help="Data fim para visualização"
            )
        
        st.divider()
        
        if st.button("📊 Buscar Métricas", type="primary"):
            try:
                params = {
                    "from": metrics_from.isoformat(),
                    "to": metrics_to.isoformat(),
                }
                if env_vars.get("PROJECT_ID"):
                    params["project_id"] = int(env_vars['PROJECT_ID'])
                
                response = requests.get(f"{API_BASE_URL}/metrics", params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    st.success(f"✅ {data['count']} métricas encontradas")
                    
                    if data['metrics']:
                        df = pd.DataFrame(data['metrics'])
                        
                        # Estatísticas resumidas
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                        with col_stat1:
                            st.metric("Total de Registros", len(df))
                        with col_stat2:
                            total_builds = df['builds'].sum() if 'builds' in df.columns else 0
                            st.metric("Total Builds", int(total_builds))
                        with col_stat3:
                            total_fails = df['fails'].sum() if 'fails' in df.columns else 0
                            st.metric("Total Falhas", int(total_fails))
                        with col_stat4:
                            fail_rate = (total_fails / total_builds * 100) if total_builds > 0 else 0
                            st.metric("Taxa de Falha", f"{fail_rate:.1f}%")
                        
                        st.divider()
                        
                        # Tabela
                        st.subheader("📋 Dados Detalhados")
                        st.dataframe(df, use_container_width=True)
                        
                        # Gráficos
                        if 'day' in df.columns and 'builds' in df.columns:
                            st.divider()
                            st.subheader("📊 Gráficos")
                            
                            chart_df = df.set_index('day').sort_index()
                            
                            col_chart1, col_chart2 = st.columns(2)
                            
                            with col_chart1:
                                st.line_chart(chart_df[['builds', 'fails']])
                                st.caption("Evolução de Builds e Falhas")
                            
                            with col_chart2:
                                if 'p95_duration' in chart_df.columns:
                                    st.line_chart(chart_df[['p95_duration', 'avg_duration']])
                                    st.caption("Duração (P95 e Média)")
                    else:
                        st.info("Nenhuma métrica encontrada no período")
                else:
                    st.error(f"❌ Erro: {response.status_code} - {response.text}")
                    st.info("💡 Certifique-se de que a API está rodando: `make api-start`")
            
            except requests.exceptions.ConnectionError:
                st.error("❌ Não foi possível conectar à API")
                st.info("💡 Inicie a API com: `make api-start`")
            except Exception as e:
                st.error(f"❌ Erro: {e}")
    
    # SUB-TAB 2: Predições do Modelo
    with sub_tab2:
        # Explicação sobre como as predições funcionam
        st.info("""
        **ℹ️ Como funcionam as predições:**
        
        - As predições são geradas por **job** (não por pipeline individual)
        - O sistema agrega todos os pipelines/jobs e cria uma feature por `job_name` único
        - Se você tem 8 jobs únicos no projeto, haverá 8 features e 8 predições
        - Cada predição representa o comportamento agregado de um job ao longo do tempo
        
        **Exemplo:** Se você tem 100 pipelines mas apenas 8 jobs únicos (ex: `build`, `test`, `deploy`, etc.),
        o sistema gerará 8 predições (uma para cada job).
        """)
        
        use_date_filter = st.checkbox("Filtrar por data", value=False, key="use_pred_date_filter")
        
        if use_date_filter:
            col_pred1, col_pred2 = st.columns(2)
            
            with col_pred1:
                pred_from = st.date_input(
                    "Data Início",
                    value=date.today() - timedelta(days=30),
                    key="pred_from",
                    help="Data início para visualização"
                )
            
            with col_pred2:
                pred_to = st.date_input(
                    "Data Fim",
                    value=date.today() + timedelta(days=1),  # Inclui hoje
                    key="pred_to",
                    help="Data fim para visualização (inclui o dia inteiro)"
                )
        else:
            pred_from = None
            pred_to = None
            st.info("ℹ️ Buscando todas as predições (sem filtro de data)")
        
        st.divider()
        
        # Botão para gerar predições em lote
        col_gen1, col_gen2 = st.columns([2, 1])
        with col_gen1:
            st.info("💡 **Dica:** Gere predições em lote a partir das features existentes. O número de predições será igual ao número de jobs únicos no projeto.")
        with col_gen2:
            if st.button("🚀 Gerar Predições em Lote", type="secondary"):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/predictions/generate",
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ {data.get('count', 0)} predições geradas!")
                        if data.get('errors', 0) > 0:
                            st.warning(f"⚠️ {data['errors']} erros durante a geração")
                    else:
                        st.error(f"❌ Erro: {response.status_code} - {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Não foi possível conectar à API")
                except Exception as e:
                    st.error(f"❌ Erro: {e}")
        
        st.divider()
        
        if st.button("📊 Buscar Predições", type="primary"):
            try:
                params = {
                    "mode": "actual"
                }
                
                if use_date_filter and pred_from:
                    params["from"] = pred_from.isoformat()
                if use_date_filter and pred_to:
                    params["to"] = pred_to.isoformat()
                
                response = requests.get(f"{API_BASE_URL}/predictions", params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    st.success(f"✅ {data['count']} predições encontradas")
                    
                    # Mostra informação sobre quantos jobs únicos existem
                    try:
                        import psycopg2
                        conn = psycopg2.connect(db_url)
                        with conn.cursor() as cur:
                            cur.execute("SELECT COUNT(DISTINCT entity_key) FROM features_online")
                            features_count = cur.fetchone()[0]
                            if features_count > 0:
                                st.caption(f"ℹ️ {features_count} jobs únicos encontrados em features_online (cada job gera uma predição)")
                        conn.close()
                    except Exception:
                        pass
                    
                    if data['predictions']:
                        df = pd.DataFrame(data['predictions'])
                        
                        # Estatísticas resumidas
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                        with col_stat1:
                            st.metric("Total", len(df))
                        with col_stat2:
                            anomalies = df[df['label'] == 'anomaly'].shape[0] if 'label' in df.columns else 0
                            st.metric("Anomalias", anomalies, delta=f"{(anomalies/len(df)*100):.1f}%")
                        with col_stat3:
                            if 'score' in df.columns:
                                avg_score = df['score'].mean()
                                st.metric("Score Médio", f"{avg_score:.3f}")
                        with col_stat4:
                            st.metric("Modelo", f"v{data.get('model_version', 'N/A')}")
                        
                        st.divider()
                        
                        # Filtro: mostrar apenas anomalias ou todas
                        show_only_anomalies = st.checkbox("Mostrar apenas anomalias", value=False)
                        
                        if show_only_anomalies:
                            df_display = df[df['label'] == 'anomaly'].copy()
                            st.info(f"🔍 Mostrando {len(df_display)} anomalias de {len(df)} predições")
                        else:
                            df_display = df.copy()
                        
                        # Tabela de predições
                        st.subheader("📋 Predições")
                        
                        # Prepara colunas para exibição
                        display_cols = ['run_id', 'label', 'score', 'model_version', 'created_at']
                        if all(col in df_display.columns for col in display_cols):
                            st.dataframe(
                                df_display[display_cols].sort_values('score', ascending=True),
                                use_container_width=True
                            )
                            
                            # Detalhes das anomalias
                            if show_only_anomalies or anomalies > 0:
                                st.divider()
                                st.subheader("⚠️ Anomalias Detectadas")
                                
                                anomalies_df = df_display[df_display['label'] == 'anomaly'] if not show_only_anomalies else df_display
                                
                                for idx, row in anomalies_df.iterrows():
                                    with st.expander(f"🔴 {row['run_id']} - Score: {row['score']:.3f}"):
                                        col_det1, col_det2 = st.columns(2)
                                        
                                        with col_det1:
                                            st.write(f"**Run ID:** `{row['run_id']}`")
                                            st.write(f"**Label:** {row['label']}")
                                            st.write(f"**Score:** {row['score']:.3f}")
                                            st.write(f"**Modelo:** v{row.get('model_version', 'N/A')}")
                                        
                                        with col_det2:
                                            if 'prediction' in row and isinstance(row['prediction'], dict):
                                                pred_dict = row['prediction']
                                                if 'features' in pred_dict:
                                                    st.write("**Features:**")
                                                    for feat, val in pred_dict['features'].items():
                                                        st.write(f"- {feat}: {val:.2f}")
                                        
                                        # Recomendação baseada no score
                                        if row['score'] < -0.5:
                                            st.warning("⚠️ **Anomalia crítica detectada!**")
                                            st.info("💡 **Recomendações:**")
                                            st.write("- Verificar logs do pipeline no GitLab")
                                            st.write("- Analisar jobs que falharam")
                                            st.write("- Revisar configurações de cache e dependências")
                        else:
                            st.dataframe(df_display, use_container_width=True)
                    else:
                        st.info("Nenhuma predição encontrada no período")
                        st.info("💡 Execute o ETL e treine um modelo primeiro")
                else:
                    st.error(f"❌ Erro: {response.status_code} - {response.text}")
                    st.info("💡 Certifique-se de que a API está rodando: `make api-start`")
            
            except requests.exceptions.ConnectionError:
                st.error("❌ Não foi possível conectar à API")
                st.info("💡 Inicie a API com: `make api-start`")
            except Exception as e:
                st.error(f"❌ Erro: {e}")
    
    # SUB-TAB 3: Erros das Pipelines
    with sub_tab3:
        st.subheader("❌ Erros das Pipelines")
        st.caption("Visualize erros detalhados das pipelines para identificar problemas e gerar insights")
        
        # Verifica se há erros no banco
        try:
            import psycopg2
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM jobs_raw 
                    WHERE project_id = %s 
                      AND status = 'failed' 
                      AND failure_reason IS NOT NULL
                """, (env_vars.get('PROJECT_ID'),))
                error_count = cur.fetchone()[0]
                
                if error_count == 0:
                    st.warning("⚠️ **Nenhum erro encontrado no banco de dados.**")
                    st.info("💡 **Dica:** Se você acabou de adicionar esta funcionalidade, pode ser que os dados já coletados não tenham o campo `failure_reason`. Nesse caso:")
                    st.write("1. Execute a coleta novamente: **📥 Obter Dados** → Coletar e Armazenar Dados")
                    st.write("2. Execute o ETL: **🔄 Processar Dados** → Executar ETL Incremental")
                else:
                    st.success(f"✅ {error_count} erros encontrados no banco de dados")
            conn.close()
        except Exception as e:
            st.warning(f"⚠️ Não foi possível verificar erros no banco: {e}")
        
        st.divider()
        
        # Filtros de data
        col_err1, col_err2 = st.columns(2)
        
        with col_err1:
            errors_from = st.date_input(
                "Data Início",
                value=date.today() - timedelta(days=30),
                key="errors_from",
                help="Data início para visualização de erros"
            )
        
        with col_err2:
            errors_to = st.date_input(
                "Data Fim",
                value=date.today() + timedelta(days=1),
                key="errors_to",
                help="Data fim para visualização de erros"
            )
        
        st.divider()
        
        # Botões para buscar erros
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("📋 Buscar Erros Detalhados", type="primary"):
                try:
                    # Verifica se a API está rodando
                    try:
                        health_response = requests.get(f"{API_BASE_URL}/healthz", timeout=5)
                        if health_response.status_code != 200:
                            st.error(f"❌ API não está respondendo corretamente (status: {health_response.status_code})")
                            st.info(f"💡 Verifique se a API está rodando em: {API_BASE_URL}")
                            st.info("💡 Inicie a API com: `make api-start`")
                            st.stop()
                    except requests.exceptions.ConnectionError:
                        st.error(f"❌ Não foi possível conectar à API em: {API_BASE_URL}")
                        st.info("💡 Verifique se a API está rodando: `make api-start`")
                        st.info(f"💡 URL configurada: {API_BASE_URL}")
                        st.stop()
                    except Exception as e:
                        st.warning(f"⚠️ Erro ao verificar API: {e}")
                    
                    params = {
                        "from": errors_from.isoformat(),
                        "to": errors_to.isoformat(),
                        "limit": 200
                    }
                    if env_vars.get("PROJECT_ID"):
                        params["project_id"] = int(env_vars['PROJECT_ID'])
                    
                    st.info(f"🔍 Buscando erros em: {API_BASE_URL}/errors")
                    response = requests.get(f"{API_BASE_URL}/errors", params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ {data['count']} erros encontrados")
                        
                        if data['errors']:
                            df_errors = pd.DataFrame(data['errors'])
                            
                            # Estatísticas resumidas
                            col_stat1, col_stat2, col_stat3 = st.columns(3)
                            with col_stat1:
                                st.metric("Total de Erros", len(df_errors))
                            with col_stat2:
                                unique_jobs = df_errors['job_name'].nunique() if 'job_name' in df_errors.columns else 0
                                st.metric("Jobs com Erro", unique_jobs)
                            with col_stat3:
                                unique_pipelines = df_errors['pipeline_id'].nunique() if 'pipeline_id' in df_errors.columns else 0
                                st.metric("Pipelines com Erro", unique_pipelines)
                            
                            st.divider()
                            
                            # Filtro por job
                            if 'job_name' in df_errors.columns:
                                unique_jobs_list = ['Todos'] + sorted(df_errors['job_name'].unique().tolist())
                                selected_job = st.selectbox("Filtrar por Job", unique_jobs_list)
                                
                                if selected_job != 'Todos':
                                    df_errors = df_errors[df_errors['job_name'] == selected_job]
                            
                            # Tabela de erros
                            st.subheader("📋 Detalhes dos Erros")
                            
                            # Prepara colunas para exibição
                            display_cols = ['pipeline_id', 'job_name', 'stage', 'failure_reason', 'retry_count', 'created_at']
                            available_cols = [col for col in display_cols if col in df_errors.columns]
                            
                            if available_cols:
                                st.dataframe(
                                    df_errors[available_cols].sort_values('created_at', ascending=False),
                                    use_container_width=True,
                                    height=400
                                )
                                
                                # Detalhes expandidos
                                st.divider()
                                st.subheader("🔍 Detalhes Expandidos")
                                
                                for idx, row in df_errors.head(20).iterrows():
                                    with st.expander(f"🔴 Pipeline #{row.get('pipeline_id', 'N/A')} - {row.get('job_name', 'N/A')}"):
                                        col_det1, col_det2 = st.columns(2)
                                        
                                        with col_det1:
                                            st.write(f"**Pipeline ID:** `{row.get('pipeline_id', 'N/A')}`")
                                            st.write(f"**Job:** `{row.get('job_name', 'N/A')}`")
                                            st.write(f"**Stage:** `{row.get('stage', 'N/A')}`")
                                            st.write(f"**Retry Count:** {row.get('retry_count', 0)}")
                                            st.write(f"**Data:** {row.get('created_at', 'N/A')}")
                                        
                                        with col_det2:
                                            if row.get('pipeline_url'):
                                                st.markdown(f"[🔗 Ver Pipeline no GitLab]({row['pipeline_url']})")
                                            if row.get('job_url'):
                                                st.markdown(f"[🔗 Ver Job no GitLab]({row['job_url']})")
                                        
                                        # Mensagem de erro
                                        if row.get('failure_reason'):
                                            st.divider()
                                            st.write("**Mensagem de Erro:**")
                                            st.code(row['failure_reason'], language=None)
                                            
                                            # Insights básicos baseados no erro
                                            error_msg = str(row['failure_reason']).lower()
                                            insights = []
                                            
                                            if 'timeout' in error_msg or 'timed out' in error_msg:
                                                insights.append("⏱️ **Timeout detectado** - Pipeline levou muito tempo")
                                            if 'no module' in error_msg or 'cannot import' in error_msg:
                                                insights.append("📦 **Dependência faltando** - Verificar requirements.txt")
                                            if 'connection' in error_msg or 'network' in error_msg:
                                                insights.append("🌐 **Problema de rede** - Verificar conectividade")
                                            if 'permission' in error_msg or 'access denied' in error_msg:
                                                insights.append("🔒 **Problema de permissão** - Verificar credenciais")
                                            if 'test' in error_msg and 'fail' in error_msg:
                                                insights.append("❌ **Teste falhou** - Revisar testes")
                                            
                                            if insights:
                                                st.info("💡 **Insights:**\n" + "\n".join(insights))
                            else:
                                st.dataframe(df_errors, use_container_width=True)
                        else:
                            st.info("✅ Nenhum erro encontrado no período!")
                    elif response.status_code == 404:
                        st.error(f"❌ Endpoint não encontrado (404)")
                        st.warning("💡 O endpoint `/errors` não foi encontrado na API.")
                        st.info("💡 Verifique se a API foi reiniciada após as mudanças recentes.")
                        st.info(f"💡 URL tentada: {API_BASE_URL}/errors")
                        st.info("💡 Reinicie a API: `make api-stop && make api-start`")
                        try:
                            st.json(response.json())
                        except:
                            st.code(response.text)
                    else:
                        st.error(f"❌ Erro: {response.status_code} - {response.text}")
                        st.info("💡 Certifique-se de que a API está rodando: `make api-start`")
                        try:
                            st.json(response.json())
                        except:
                            st.code(response.text)
                
                except requests.exceptions.ConnectionError:
                    st.error("❌ Não foi possível conectar à API")
                    st.info("💡 Inicie a API com: `make api-start`")
                except Exception as e:
                    st.error(f"❌ Erro: {e}")
        
        with col_btn2:
            if st.button("📊 Resumo de Erros", type="secondary"):
                try:
                    # Verifica se a API está rodando
                    try:
                        health_response = requests.get(f"{API_BASE_URL}/healthz", timeout=5)
                        if health_response.status_code != 200:
                            st.error(f"❌ API não está respondendo corretamente (status: {health_response.status_code})")
                            st.info(f"💡 Verifique se a API está rodando em: {API_BASE_URL}")
                            st.info("💡 Inicie a API com: `make api-start`")
                            st.stop()
                    except requests.exceptions.ConnectionError:
                        st.error(f"❌ Não foi possível conectar à API em: {API_BASE_URL}")
                        st.info("💡 Verifique se a API está rodando: `make api-start`")
                        st.info(f"💡 URL configurada: {API_BASE_URL}")
                        st.stop()
                    except Exception as e:
                        st.warning(f"⚠️ Erro ao verificar API: {e}")
                    
                    params = {
                        "from": errors_from.isoformat(),
                        "to": errors_to.isoformat()
                    }
                    if env_vars.get("PROJECT_ID"):
                        params["project_id"] = int(env_vars['PROJECT_ID'])
                    
                    st.info(f"🔍 Buscando resumo de erros em: {API_BASE_URL}/errors/summary")
                    response = requests.get(f"{API_BASE_URL}/errors/summary", params=params, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ Resumo de {data['count']} jobs com erros")
                        
                        if data['summary']:
                            df_summary = pd.DataFrame(data['summary'])
                            
                            # Gráfico de erros por job
                            st.subheader("📊 Erros por Job")
                            
                            col_chart1, col_chart2 = st.columns(2)
                            
                            with col_chart1:
                                chart_df = df_summary.set_index('job_name')[['total_fails']].sort_values('total_fails', ascending=False)
                                st.bar_chart(chart_df)
                                st.caption("Total de Falhas por Job")
                            
                            with col_chart2:
                                chart_df2 = df_summary.set_index('job_name')[['fail_rate']].sort_values('fail_rate', ascending=False)
                                st.bar_chart(chart_df2)
                                st.caption("Taxa de Falha (%) por Job")
                            
                            st.divider()
                            
                            # Tabela de resumo
                            st.subheader("📋 Resumo Detalhado")
                            
                            # Expandir error_types
                            summary_display = []
                            for _, row in df_summary.iterrows():
                                error_types = row.get('error_types', {})
                                if isinstance(error_types, dict):
                                    error_types_str = ", ".join([f"{k}: {v}" for k, v in list(error_types.items())[:5]])
                                else:
                                    error_types_str = str(error_types)[:200]
                                
                                summary_display.append({
                                    'Job': row['job_name'],
                                    'Total Falhas': row['total_fails'],
                                    'Total Builds': row['total_builds'],
                                    'Taxa de Falha (%)': f"{row['fail_rate']:.1f}%",
                                    'Tipos de Erro (Top 5)': error_types_str
                                })
                            
                            df_display = pd.DataFrame(summary_display)
                            st.dataframe(df_display, use_container_width=True)
                            
                            # Insights por job
                            st.divider()
                            st.subheader("💡 Insights por Job")
                            
                            for _, row in df_summary.iterrows():
                                with st.expander(f"🔍 {row['job_name']} - {row['total_fails']} falhas ({row['fail_rate']:.1f}%)"):
                                    st.write(f"**Total de Builds:** {row['total_builds']}")
                                    st.write(f"**Total de Falhas:** {row['total_fails']}")
                                    st.write(f"**Taxa de Falha:** {row['fail_rate']:.1f}%")
                                    
                                    error_types = row.get('error_types', {})
                                    if isinstance(error_types, dict) and error_types:
                                        st.write("**Tipos de Erro Mais Comuns:**")
                                        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                                            st.write(f"- `{error_type}`: {count} ocorrências")
                                    
                                    # Recomendações baseadas na taxa de falha
                                    if row['fail_rate'] > 50:
                                        st.warning("⚠️ **Taxa de falha muito alta!** Considere revisar a configuração deste job.")
                                    elif row['fail_rate'] > 20:
                                        st.info("ℹ️ **Taxa de falha moderada.** Verifique os tipos de erro mais comuns acima.")
                        else:
                            st.info("✅ Nenhum erro encontrado no período!")
                    elif response.status_code == 404:
                        st.error(f"❌ Endpoint não encontrado (404)")
                        st.warning("💡 O endpoint `/errors/summary` não foi encontrado na API.")
                        st.info("💡 Verifique se a API foi reiniciada após as mudanças recentes.")
                        st.info(f"💡 URL tentada: {API_BASE_URL}/errors/summary")
                        st.info("💡 Reinicie a API: `make api-stop && make api-start`")
                        try:
                            st.json(response.json())
                        except:
                            st.code(response.text)
                    else:
                        st.error(f"❌ Erro: {response.status_code} - {response.text}")
                        try:
                            st.json(response.json())
                        except:
                            st.code(response.text)
                
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Não foi possível conectar à API em: {API_BASE_URL}")
                    st.info("💡 Verifique se a API está rodando: `make api-start`")
                except Exception as e:
                    st.error(f"❌ Erro: {e}")
                    st.exception(e)

# ================================================================
# FOOTER
# ================================================================

st.divider()
st.caption("💡 Dica: Configure todas as variáveis no sidebar antes de usar as funcionalidades.")
