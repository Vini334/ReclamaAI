# Guia de Setup - ReclamaAI

Este guia detalha como configurar o ambiente de desenvolvimento e os serviços Azure necessários.

## 1. Pré-requisitos

### 1.1 Ferramentas Locais

```bash
# Python 3.11+
python --version  # deve mostrar 3.11.x ou superior

# Docker e Docker Compose
docker --version
docker-compose --version

# Git
git --version

# Azure CLI (opcional, mas recomendado)
az --version
```

### 1.2 Contas Necessárias

- [x] Conta Azure com créditos ($200 free tier)
- [ ] Conta LangSmith (gratuita): https://smith.langchain.com
- [ ] Conta GitHub (para CI/CD)

## 2. Configuração do Azure

### 2.1 Resource Group

Já criado: `reclamaAI` (East US)

### 2.2 Azure OpenAI

1. Acesse o [Azure Portal](https://portal.azure.com)
2. Vá para o recurso Azure OpenAI criado
3. No menu lateral, clique em **Model deployments** > **Manage Deployments**
4. Clique em **Create new deployment**:
   - **Model**: gpt-4o-mini
   - **Deployment name**: `gpt-4o-mini` (use este nome exato)
   - **Deployment type**: Standard
5. Anote:
   - **Endpoint**: `https://seu-recurso.openai.azure.com/`
   - **API Key**: Disponível em "Keys and Endpoint"

### 2.3 Azure AI Search

1. No Azure Portal, busque "AI Search"
2. Clique em **Create**:
   - **Resource Group**: reclamaAI
   - **Service name**: `reclamai-search`
   - **Location**: East US
   - **Pricing tier**: Basic ($25/mês)
3. Após criar, anote:
   - **Endpoint**: `https://reclamai-search.search.windows.net`
   - **Admin Key**: Disponível em "Keys"

### 2.4 Azure Cosmos DB

1. No Azure Portal, busque "Azure Cosmos DB"
2. Clique em **Create** > **Azure Cosmos DB for NoSQL**
3. Configure:
   - **Resource Group**: reclamaAI
   - **Account Name**: `reclamai-cosmos`
   - **Location**: East US
   - **Capacity mode**: **Serverless** (importante para economizar)
4. Após criar, anote:
   - **URI**: `https://reclamai-cosmos.documents.azure.com:443/`
   - **Primary Key**: Disponível em "Keys"

### 2.5 Application Insights (Observabilidade)

1. No Azure Portal, busque "Application Insights"
2. Clique em **Create**:
   - **Resource Group**: reclamaAI
   - **Name**: `reclamai-insights`
   - **Region**: East US
3. Após criar, anote:
   - **Connection String**: Disponível em "Overview"

## 3. Configuração do LangSmith

### 3.1 Criar Conta

1. Acesse https://smith.langchain.com
2. Faça login com GitHub ou Google
3. Crie um novo projeto: `reclamaai`

### 3.2 Obter API Key

1. Clique no ícone de usuário > Settings
2. Vá em "API Keys"
3. Clique em "Create API Key"
4. Anote a chave gerada

### 3.3 Como usar o LangSmith

O LangSmith oferece:
- **Tracing**: Visualização de cada chamada LLM
- **Debugging**: Inspecionar prompts e respostas
- **Evaluation**: Testar qualidade dos outputs
- **Monitoring**: Métricas de latência e custo

Dashboard: https://smith.langchain.com/o/seu-org/projects/p/reclamaai

## 4. Configuração Local

### 4.1 Clonar e Configurar

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/reclamaAI.git
cd reclamaAI

# Criar ambiente virtual
python -m venv venv

# Ativar ambiente (Linux/Mac)
source venv/bin/activate

# Ativar ambiente (Windows)
venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### 4.2 Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar com suas credenciais
nano .env  # ou use seu editor preferido
```

### 4.3 Conteúdo do .env

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://seu-recurso.openai.azure.com/
AZURE_OPENAI_API_KEY=sua-chave-aqui
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://reclamai-search.search.windows.net
AZURE_SEARCH_API_KEY=sua-chave-admin
AZURE_SEARCH_INDEX_NAME=teams-index

# Azure Cosmos DB
COSMOS_ENDPOINT=https://reclamai-cosmos.documents.azure.com:443/
COSMOS_KEY=sua-primary-key
COSMOS_DATABASE_NAME=reclamaai
COSMOS_CONTAINER_NAME=complaints

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=sua-langsmith-key
LANGCHAIN_PROJECT=reclamaai

# Azure Monitor
APPLICATIONINSIGHTS_CONNECTION_STRING=sua-connection-string

# App Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## 5. Executando o Projeto

### 5.1 Modo Desenvolvimento

```bash
# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Executar API
uvicorn src.api.main:app --reload --port 8000

# Acessar documentação
# http://localhost:8000/docs
```

### 5.2 Com Docker

```bash
# Construir imagem
docker-compose build

# Executar
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar
docker-compose down
```

### 5.3 Executar Testes

```bash
# Todos os testes
pytest tests/ -v

# Apenas unit tests
pytest tests/unit/ -v

# Com coverage
pytest tests/ --cov=src --cov-report=html
```

## 6. Verificação do Setup

### 6.1 Checklist

Execute cada comando para verificar se o setup está correto:

```bash
# 1. Verificar conexão Azure OpenAI
python -c "
from openai import AzureOpenAI
import os
from dotenv import load_dotenv
load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version=os.getenv('AZURE_OPENAI_API_VERSION')
)
response = client.chat.completions.create(
    model=os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME'),
    messages=[{'role': 'user', 'content': 'Olá!'}],
    max_tokens=10
)
print('✅ Azure OpenAI OK:', response.choices[0].message.content)
"

# 2. Verificar LangSmith
python -c "
from langsmith import Client
client = Client()
print('✅ LangSmith OK - Projetos:', [p.name for p in client.list_projects()])
"

# 3. Verificar Azure AI Search
python -c "
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
from dotenv import load_dotenv
load_dotenv()

client = SearchClient(
    endpoint=os.getenv('AZURE_SEARCH_ENDPOINT'),
    index_name='test',
    credential=AzureKeyCredential(os.getenv('AZURE_SEARCH_API_KEY'))
)
print('✅ Azure AI Search OK - Conexão estabelecida')
"

# 4. Verificar Cosmos DB
python -c "
from azure.cosmos import CosmosClient
import os
from dotenv import load_dotenv
load_dotenv()

client = CosmosClient(
    os.getenv('COSMOS_ENDPOINT'),
    os.getenv('COSMOS_KEY')
)
print('✅ Cosmos DB OK - Databases:', [db['id'] for db in client.list_databases()])
"
```

### 6.2 Problemas Comuns

| Problema | Solução |
|----------|---------|
| `AuthenticationError` no Azure OpenAI | Verificar API Key e Endpoint |
| `ResourceNotFoundError` | Modelo não foi deployed, verificar passo 2.2 |
| `Connection refused` no Cosmos | Verificar firewall do Cosmos DB |
| LangSmith não mostra traces | Verificar `LANGCHAIN_TRACING_V2=true` |

## 7. Estrutura de Custos

### Estimativa Mensal (uso moderado)

| Serviço | Custo Estimado |
|---------|----------------|
| Azure OpenAI (GPT-4o-mini) | $5-10 |
| Azure AI Search (Basic) | $25 |
| Cosmos DB (Serverless) | $5-10 |
| Application Insights | $0-5 |
| Container Apps | Free tier |
| **Total** | **~$35-50/mês** |

### Dicas para Economizar

1. **Cosmos DB**: Use Serverless (paga por uso)
2. **Azure OpenAI**: GPT-4o-mini é 15x mais barato que GPT-4
3. **AI Search**: Basic tier é suficiente para o projeto
4. **Logs**: Configure retenção mínima no App Insights

## 8. Próximos Passos

Após configurar o ambiente:

1. [ ] Verificar todos os checkpoints do item 6.1
2. [ ] Criar índice no Azure AI Search (script será fornecido)
3. [ ] Popular Cosmos DB com dados iniciais
4. [ ] Executar primeiro teste end-to-end
