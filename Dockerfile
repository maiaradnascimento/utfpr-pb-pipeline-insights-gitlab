FROM python:3.11-slim

# Instala dependências do sistema se necessário
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho
WORKDIR /app

# Copia o requirements.txt
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cria os diretórios necessários (figuras agora vivem dentro de dados/processed/<PROJECT_ID>/figuras)
RUN mkdir -p dados/raw dados/processed models/transformers models/schemas

# O código fonte será montado via volume
# Não copiamos aqui para permitir desenvolvimento iterativo

# Define o usuário não-root para segurança (opcional)
# RUN useradd -m -u 1000 tccuser
# USER tccuser

CMD ["python", "--version"]

