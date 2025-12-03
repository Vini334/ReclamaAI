# ReclamaAI

Sistema multiagente para gestão automática de reclamações de e-commerce, utilizando LLM, RAG e orquestração de agentes.

## Visão Geral

O ReclamaAI automatiza o fluxo de tratamento de reclamações da **TechNova Store** (e-commerce fictício), unificando dados de múltiplas fontes e utilizando IA para classificar, rotear e criar tickets automaticamente.

### Funcionalidades Implementadas

- **Coleta Unificada**: Ingere reclamações de Reclame Aqui, Jira, Chat, WhatsApp, Telefone e E-mail (dados mock)
- **Conformidade LGPD**: Mascara CPF, email, telefone e cartão antes do processamento LLM
- **Análise com LLM**: Resume, classifica categoria/sentimento/urgência usando Azure OpenAI (GPT-4o-mini)
- **Roteamento Inteligente**: Direciona ao time correto baseado na categoria
- **Automação**: Cria tickets no Jira e envia notificações por e-mail (mock)
- **Persistência**: Armazena reclamações e audit log no Azure Cosmos DB
- **Observabilidade**: Tracing detalhado com LangSmith (prompts, respostas, tokens, latência)

## Stack Tecnológica

| Categoria | Tecnologia |
|-----------|------------|
| **Linguagem** | Python 3.8+ |
| **API** | FastAPI |
| **LLM** | Azure OpenAI (GPT-4o-mini) |
| **RAG** | Azure AI Search (em desenvolvimento) |
| **Banco de Dados** | Azure Cosmos DB (Serverless) |
| **Observabilidade** | LangSmith |
| **Containers** | Docker |

## Arquitetura de Agentes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORQUESTRADOR                                       │
│         NEW → ANONYMIZED → ANALYZED → ROUTED → TICKET_CREATED → COMPLETED   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
    ┌───────────┬───────────┬───────┴───────┬───────────┬───────────┐
    ▼           ▼           ▼               ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Coletor │→│Privacy │→│ Analista │→│ Roteador │→│ Comunic. │→│ Cosmos   │
│(Ingest)│ │ (LGPD) │ │  (LLM)   │ │          │ │(Jira+Email)│ │   DB    │
└────────┘ └────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

### Times de Roteamento

| Time | Categorias |
|------|------------|
| Logística | Atraso na entrega, Produto não entregue |
| Financeiro | Cobrança indevida, Reembolso não processado |
| Produtos | Produto com defeito, Produto diferente do anunciado |
| Atendimento N2 | Atendimento ruim, Cancelamento negado, Dificuldade de contato |
| Marketplace | Problema com vendedor |

## Estrutura do Projeto

```
reclamaAI/
├── src/
│   ├── agents/             # Agentes especializados
│   │   ├── collector.py    # Coleta de múltiplas fontes
│   │   ├── privacy.py      # Anonimização LGPD
│   │   ├── analyst.py      # Análise com LLM
│   │   ├── router.py       # Roteamento para times
│   │   └── communicator.py # Tickets e notificações
│   ├── api/                # Endpoints FastAPI
│   │   ├── main.py
│   │   └── routes/
│   ├── core/               # Configurações
│   │   └── config.py
│   ├── integrations/       # Azure OpenAI, Search, Jira, Email
│   ├── models/             # Schemas Pydantic
│   ├── services/           # Orchestrator, Cosmos, MockData
│   │   ├── orchestrator.py
│   │   ├── cosmos_service.py
│   │   └── mock_data_loader.py
│   └── utils/              # Prompts, LangSmith config
├── tests/
│   └── test_privacy_agent.py  # 20 testes unitários
├── data/
│   └── mock/               # 105 reclamações simuladas
├── scripts/
│   ├── init_cosmos.py      # Inicializa Cosmos DB
│   └── test_connections.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Início Rápido

### Pré-requisitos

- Python 3.8+
- Docker e Docker Compose (opcional)
- Conta Azure com:
  - Azure OpenAI (deployment GPT-4o-mini)
  - Azure Cosmos DB (Serverless)
- Conta LangSmith (gratuita em smith.langchain.com)

### Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/reclamaAI.git
cd reclamaAI

# Crie o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas credenciais
```

### Inicializar Cosmos DB

```bash
# Verifica conexão
python scripts/init_cosmos.py --verify

# Cria database, containers e popula times
python scripts/init_cosmos.py

# Mostra estatísticas
python scripts/init_cosmos.py --stats
```

### Executar a API

```bash
# Com uvicorn (desenvolvimento)
uvicorn src.api.main:app --reload --port 8000

# Com Docker
docker-compose up -d

# Acesse a documentação
# http://localhost:8000/docs
```

### Executar Testes

```bash
# Todos os testes
pytest tests/ -v

# Apenas testes do Privacy Agent
pytest tests/test_privacy_agent.py -v

# Com cobertura
pytest tests/ --cov=src --cov-report=html
```

## Como Testar

### 1. Processar uma Reclamação via API

```bash
# Processar reclamação única
curl -X POST "http://localhost:8000/api/v1/complaints/process-single" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "TEST-001",
    "source": "reclame_aqui",
    "title": "Pedido não chegou",
    "description": "Comprei há 15 dias e não recebi. Meu CPF é 123.456.789-00",
    "consumer_name": "João Silva",
    "consumer_contact": "joao@email.com",
    "created_at": "2025-01-15T10:00:00Z",
    "channel": "web"
  }'

# Listar reclamações processadas
curl "http://localhost:8000/api/v1/complaints"

# Buscar reclamação específica
curl "http://localhost:8000/api/v1/complaints/{id}"

# Ver estatísticas
curl "http://localhost:8000/api/v1/complaints/stats/summary"
```

### 2. Processar Lote de Reclamações

```bash
# Processa 5 reclamações do mock
curl -X POST "http://localhost:8000/api/v1/complaints/process" \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'

# Filtrar por fonte
curl -X POST "http://localhost:8000/api/v1/complaints/process" \
  -H "Content-Type: application/json" \
  -d '{"source": "reclame_aqui", "limit": 10}'
```

### 3. Verificar Traces no LangSmith

1. Acesse: https://smith.langchain.com/
2. Navegue até o projeto: `reclamaai`
3. Você verá traces com:
   - **Run name**: `analyze_complaint_*`
   - **Metadata**: complaint_id, source, agent
   - **Tags**: reclamaai, analyst, source:{fonte}
4. Clique no trace para ver:
   - Prompt enviado (system + user)
   - Resposta do LLM (JSON)
   - Tokens usados
   - Latência

### 4. Verificar Dados no Cosmos DB

```bash
# Via script
python scripts/init_cosmos.py --stats

# Ou no Azure Portal:
# 1. Acesse portal.azure.com
# 2. Navegue até sua conta Cosmos DB
# 3. Clique em "Data Explorer"
# 4. Explore os containers: complaints, audit_log, teams
```

### 5. Testar via Python

```python
import asyncio
from datetime import datetime
from src.services.orchestrator import ComplaintOrchestrator
from src.models.schemas import ComplaintRaw, ComplaintSource

async def test():
    complaint = ComplaintRaw(
        external_id="TEST-001",
        source=ComplaintSource.CHAT,
        title="Produto com defeito",
        description="Notebook com tela quebrada",
        consumer_name="Teste",
        created_at=datetime.utcnow(),
        channel="chat",
    )

    orchestrator = ComplaintOrchestrator()
    result = await orchestrator.process_complaint(complaint)

    print(f"Status: {result.workflow_status.value}")
    print(f"Categoria: {result.complaint_analyzed.category.value}")
    print(f"Time: {result.routing_decision.team}")

asyncio.run(test())
```

## Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

### Azure OpenAI (obrigatório)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `AZURE_OPENAI_ENDPOINT` | URL do recurso Azure OpenAI | `https://seu-recurso.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | Chave de API | `abc123...` |
| `AZURE_OPENAI_API_VERSION` | Versão da API | `2024-02-15-preview` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Nome do deployment | `gpt-4o-mini` |

### Azure Cosmos DB (obrigatório para persistência)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `COSMOS_ENDPOINT` | URL do Cosmos DB | `https://xxx.documents.azure.com:443/` |
| `COSMOS_KEY` | Primary key | `abc123...` |
| `COSMOS_DATABASE_NAME` | Nome do database | `reclamaai` |

### LangSmith (obrigatório para tracing)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `LANGCHAIN_TRACING_V2` | Habilita tracing | `true` |
| `LANGCHAIN_ENDPOINT` | URL da API | `https://api.smith.langchain.com` |
| `LANGCHAIN_API_KEY` | API key do LangSmith | `ls__abc123...` |
| `LANGCHAIN_PROJECT` | Nome do projeto | `reclamaai` |

### Azure AI Search (opcional - para RAG)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `AZURE_SEARCH_ENDPOINT` | URL do Search | `https://xxx.search.windows.net` |
| `AZURE_SEARCH_API_KEY` | Admin key | `abc123...` |
| `AZURE_SEARCH_INDEX_NAME` | Nome do índice | `teams-index` |

### Aplicação

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `ENVIRONMENT` | Ambiente de execução | `development` / `production` |
| `LOG_LEVEL` | Nível de log | `INFO` / `DEBUG` |
| `API_HOST` | Host da API | `0.0.0.0` |
| `API_PORT` | Porta da API | `8000` |
| `USE_MOCK_JIRA` | Usar mock do Jira | `true` |
| `USE_MOCK_EMAIL` | Usar mock de email | `true` |

## Roadmap

### MVP (Fase 1) - Concluído
- [x] Estrutura do projeto
- [x] Agente Coletor (5 fontes mock)
- [x] Agente Privacy (LGPD - CPF, email, telefone, cartão)
- [x] Agente Analista (Azure OpenAI GPT-4o-mini)
- [x] Agente Roteador (5 times)
- [x] Agente Comunicador (mock Jira + email)
- [x] API FastAPI com endpoints REST
- [x] Integração Azure OpenAI
- [x] Persistência Azure Cosmos DB
- [x] Observabilidade LangSmith
- [x] Docker

### Fase 2 - Em Desenvolvimento
- [ ] Roteamento com RAG (Azure AI Search)
- [ ] Agente de QA (validação de análises)
- [ ] Dashboard de monitoramento
- [ ] Métricas e alertas (Azure Monitor)
- [ ] Deploy Azure Container Apps
- [ ] CI/CD com GitHub Actions

### Fase 3 - Planejado
- [ ] Agente Monitor (observabilidade avançada)
- [ ] Agente de Aprendizado Contínuo
- [ ] A/B testing de prompts
- [ ] Integração real com Jira/Email
- [ ] Frontend React

## Endpoints da API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/` | Info da API |
| GET | `/health` | Health check |
| GET | `/api/v1/complaints` | Lista reclamações |
| GET | `/api/v1/complaints/{id}` | Busca reclamação |
| POST | `/api/v1/complaints/process` | Processa lote (background) |
| POST | `/api/v1/complaints/process-single` | Processa uma (síncrono) |
| POST | `/api/v1/complaints/{id}/reprocess` | Reprocessa reclamação |
| GET | `/api/v1/complaints/stats/summary` | Estatísticas |
| GET | `/api/v1/complaints/available` | Lista mock disponível |
| GET | `/api/v1/complaints/audit/{id}` | Log de auditoria |

## Dados Mock

O projeto inclui 105 reclamações simuladas em `data/mock/`:

| Arquivo | Quantidade | Fonte |
|---------|------------|-------|
| `reclame_aqui.json` | 40 | Reclame Aqui |
| `jira_issues.json` | 20 | Jira |
| `chat_transcripts.json` | 15 | Chat/WhatsApp |
| `phone_transcripts.json` | 10 | Telefone |
| `support_emails.json` | 20 | Email |
| `teams.json` | 5 | Definição dos times |

## Licença

Este projeto é para fins educacionais e de portfólio.

---

Desenvolvido como demonstração de arquitetura multiagente com Azure AI.
