# Arquitetura do ReclamaAI

## 1. Visão Geral

O ReclamaAI é um sistema multiagente projetado para automatizar o tratamento de reclamações de e-commerce. A arquitetura segue os princípios de **MCP (Modular, Coherent, Persistent)** e **A2A (Agent-to-Agent)**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CAMADA DE API                                   │
│                            (FastAPI + REST)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAMADA DE ORQUESTRAÇÃO                               │
│                              (LangGraph)                                     │
│                                                                              │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐   │
│  │   NEW   │───▶│ANALYZED │───▶│  QA_OK  │───▶│ ROUTED  │───▶│ CREATED │   │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CAMADA DE AGENTES                                   │
│                                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  Coletor   │  │  Privacy   │  │  Analista  │  │  Roteador  │            │
│  │  Agent     │  │  Agent     │  │  Agent     │  │  Agent     │            │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
│                                                                              │
│  ┌────────────┐  ┌────────────┐                                             │
│  │ Comunicador│  │  Monitor   │                                             │
│  │  Agent     │  │  Agent     │                                             │
│  └────────────┘  └────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE INTEGRAÇÕES                                 │
│                                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   Azure    │  │   Azure    │  │   Azure    │  │   Jira     │            │
│  │  OpenAI    │  │ AI Search  │  │ Cosmos DB  │  │   Mock     │            │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
│                                                                              │
│  ┌────────────┐  ┌────────────┐                                             │
│  │   Email    │  │ LangSmith  │                                             │
│  │   Mock     │  │  Tracing   │                                             │
│  └────────────┘  └────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Princípios Arquiteturais

### 2.1 MCP (Modular, Coherent, Persistent)

| Princípio | Implementação |
|-----------|---------------|
| **Modular** | Cada agente é um módulo independente com responsabilidade única |
| **Coherent** | Orquestrador garante consistência do fluxo e estado |
| **Persistent** | Estado persiste no Cosmos DB, permitindo retomada |

### 2.2 A2A (Agent-to-Agent)

- Agentes comunicam-se através do **State** compartilhado no LangGraph
- Cada agente recebe o estado, processa, e retorna estado atualizado
- Orquestrador controla o fluxo e decide próximo agente

```python
# Exemplo de comunicação A2A via State
class ComplaintState(TypedDict):
    complaint_raw: ComplaintRaw
    complaint_analyzed: Optional[ComplaintAnalyzed]
    routing_decision: Optional[RoutingDecision]
    ticket_info: Optional[TicketInfo]
    current_step: str
    errors: List[str]
```

## 3. Detalhamento dos Agentes

### 3.1 Agente Coletor (Ingestion Agent)

**Responsabilidade:** Ingerir reclamações de múltiplas fontes simuladas.

```
┌─────────────────────────────────────────────────────────────┐
│                     AGENTE COLETOR                          │
├─────────────────────────────────────────────────────────────┤
│ Fontes de Entrada:                                          │
│ • Mock Reclame Aqui (API simulada)                         │
│ • Mock Jira (problemas existentes)                         │
│ • Mock Chat/WhatsApp (transcrições)                        │
│ • Mock Email (mensagens de suporte)                        │
├─────────────────────────────────────────────────────────────┤
│ Processamento:                                              │
│ 1. Buscar dados de cada fonte                              │
│ 2. Normalizar para schema ComplaintRaw                     │
│ 3. Verificar duplicatas no banco                           │
│ 4. Inserir novas reclamações                               │
├─────────────────────────────────────────────────────────────┤
│ Saída: List[ComplaintRaw]                                  │
└─────────────────────────────────────────────────────────────┘
```

**Tools disponíveis:**
- `fetch_reclame_aqui()`: Busca reclamações do mock
- `fetch_jira_issues()`: Busca issues do mock Jira
- `fetch_chat_transcripts()`: Busca transcrições de chat
- `fetch_support_emails()`: Busca emails de suporte
- `check_duplicate()`: Verifica se já foi processado

### 3.2 Agente Privacy (Compliance Agent)

**Responsabilidade:** Garantir conformidade LGPD.

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTE PRIVACY                           │
├─────────────────────────────────────────────────────────────┤
│ Detecção de PII:                                            │
│ • CPF: ###.###.###-##                                      │
│ • Email: ***@***.***                                       │
│ • Telefone: (##) #####-####                                │
│ • Cartão de crédito: #### **** **** ####                   │
│ • Endereço: [ENDEREÇO REMOVIDO]                            │
├─────────────────────────────────────────────────────────────┤
│ Processamento:                                              │
│ 1. Aplicar regex para detectar PII                         │
│ 2. Substituir por tokens mascarados                        │
│ 3. Manter mapeamento interno (se necessário restaurar)     │
├─────────────────────────────────────────────────────────────┤
│ Saída: ComplaintRaw com texto anonimizado                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Agente Analista (LLM Agent)

**Responsabilidade:** Analisar e classificar reclamações usando LLM.

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTE ANALISTA                          │
├─────────────────────────────────────────────────────────────┤
│ Modelo: Azure OpenAI GPT-4o-mini                           │
├─────────────────────────────────────────────────────────────┤
│ Outputs:                                                    │
│ • Resumo: 1-2 frases objetivas                             │
│ • Categoria: Uma das 10 categorias definidas               │
│ • Sentimento: neutro | insatisfeito | muito_insatisfeito   │
│ • Urgência: baixa | média | alta | crítica                 │
├─────────────────────────────────────────────────────────────┤
│ Prompt Engineering:                                         │
│ • Few-shot examples para cada categoria                    │
│ • Chain-of-thought para urgência                           │
│ • Output estruturado (JSON)                                │
├─────────────────────────────────────────────────────────────┤
│ Saída: ComplaintAnalyzed                                   │
└─────────────────────────────────────────────────────────────┘
```

**Categorias suportadas:**
1. Atraso na entrega
2. Produto não entregue
3. Produto com defeito
4. Produto diferente do anunciado
5. Cobrança indevida
6. Reembolso não processado
7. Atendimento ruim
8. Problema com vendedor (marketplace)
9. Cancelamento negado
10. Dificuldade de contato

### 3.4 Agente Roteador (RAG Agent)

**Responsabilidade:** Direcionar reclamação ao time correto.

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTE ROTEADOR                          │
├─────────────────────────────────────────────────────────────┤
│ Vector DB: Azure AI Search                                  │
├─────────────────────────────────────────────────────────────┤
│ Índice contém:                                              │
│ • Descrição dos times                                       │
│ • Responsabilidades                                         │
│ • Exemplos de casos anteriores                             │
│ • Contatos (email do responsável)                          │
├─────────────────────────────────────────────────────────────┤
│ Processamento:                                              │
│ 1. Gerar embedding do resumo + categoria                   │
│ 2. Busca semântica no índice de times                      │
│ 3. Aplicar regras de negócio (SLA, prioridade)            │
│ 4. Selecionar time mais adequado                           │
├─────────────────────────────────────────────────────────────┤
│ Saída: RoutingDecision                                     │
└─────────────────────────────────────────────────────────────┘
```

**Times disponíveis:**

| Time | Responsabilidade | Email |
|------|------------------|-------|
| Logística | Entregas, rastreamento, extravio | logistica@technova.com |
| Financeiro | Cobranças, reembolsos, estornos | financeiro@technova.com |
| Produtos | Defeitos, trocas, garantia | produtos@technova.com |
| Atendimento N2 | Casos complexos, escalações | n2@technova.com |
| Marketplace | Problemas com vendedores terceiros | marketplace@technova.com |

### 3.5 Agente Comunicador (Action Agent)

**Responsabilidade:** Executar ações externas.

```
┌─────────────────────────────────────────────────────────────┐
│                   AGENTE COMUNICADOR                        │
├─────────────────────────────────────────────────────────────┤
│ Ações:                                                      │
│ 1. Criar ticket no Jira (mock)                             │
│ 2. Enviar email de notificação (mock)                      │
│ 3. Registrar no banco de dados                             │
├─────────────────────────────────────────────────────────────┤
│ Template do Ticket:                                         │
│ • Título: [CATEGORIA] - Resumo                             │
│ • Descrição: Resumo + Texto original + Metadados           │
│ • Prioridade: Baseada na urgência                          │
│ • Assignee: Responsável do time                            │
├─────────────────────────────────────────────────────────────┤
│ Saída: TicketInfo                                          │
└─────────────────────────────────────────────────────────────┘
```

### 3.6 Agente Monitor (Observability Agent)

**Responsabilidade:** Monitorar saúde do sistema.

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTE MONITOR                           │
├─────────────────────────────────────────────────────────────┤
│ Métricas coletadas:                                         │
│ • Reclamações processadas por período                      │
│ • Taxa de erro por agente                                  │
│ • Latência de cada step                                    │
│ • Tokens consumidos (LLM)                                  │
├─────────────────────────────────────────────────────────────┤
│ Integrações:                                                │
│ • LangSmith: Tracing de LLM                                │
│ • Azure Monitor: Métricas de infra                         │
├─────────────────────────────────────────────────────────────┤
│ Alertas:                                                    │
│ • Fila > 100 reclamações pendentes                         │
│ • Taxa de erro > 5%                                        │
│ • Latência média > 30s                                     │
└─────────────────────────────────────────────────────────────┘
```

## 4. Fluxo de Estados (LangGraph)

```python
from langgraph.graph import StateGraph, END

# Definição do grafo
workflow = StateGraph(ComplaintState)

# Adicionar nós (agentes)
workflow.add_node("collect", collector_agent)
workflow.add_node("anonymize", privacy_agent)
workflow.add_node("analyze", analyst_agent)
workflow.add_node("route", router_agent)
workflow.add_node("communicate", communicator_agent)
workflow.add_node("monitor", monitor_agent)

# Definir fluxo
workflow.add_edge("collect", "anonymize")
workflow.add_edge("anonymize", "analyze")
workflow.add_edge("analyze", "route")
workflow.add_edge("route", "communicate")
workflow.add_edge("communicate", "monitor")
workflow.add_edge("monitor", END)

# Tratamento de erros
workflow.add_conditional_edges(
    "analyze",
    should_retry,
    {
        "retry": "analyze",
        "continue": "route",
        "fail": "monitor"
    }
)
```

### Estados do Workflow

| Estado | Descrição |
|--------|-----------|
| `NEW` | Reclamação recém-ingerida |
| `ANONYMIZED` | Dados sensíveis mascarados |
| `ANALYZED` | Classificada pelo LLM |
| `ROUTED` | Time definido pelo RAG |
| `TICKET_CREATED` | Ticket criado no Jira |
| `NOTIFIED` | Email enviado |
| `FAILED_*` | Estados de erro específicos |

## 5. Modelo de Dados

### 5.1 Schemas Principais

```python
class ComplaintRaw(BaseModel):
    """Reclamação bruta de qualquer fonte"""
    id: str
    external_id: str
    source: Literal["reclame_aqui", "jira", "chat", "email"]
    company_name: str
    title: str
    description: str
    consumer_name: str
    created_at: datetime
    channel: str
    city: Optional[str]
    state: Optional[str]
    product_category: Optional[str]
    status: str

class ComplaintAnalyzed(BaseModel):
    """Reclamação após análise do LLM"""
    complaint_id: str
    summary: str
    category: str
    sentiment: Literal["neutro", "insatisfeito", "muito_insatisfeito"]
    urgency: Literal["baixa", "media", "alta", "critica"]
    qa_approved: bool = False

class RoutingDecision(BaseModel):
    """Decisão de roteamento"""
    complaint_id: str
    team: str
    responsible_email: str
    priority: Literal["low", "medium", "high", "critical"]
    justification: str

class TicketInfo(BaseModel):
    """Informações do ticket criado"""
    complaint_id: str
    jira_id: str
    jira_link: str
    status: str
    created_at: datetime
```

### 5.2 Estrutura no Cosmos DB

```
Container: complaints
├── Partition Key: /source
└── Documents:
    ├── complaint_raw
    ├── complaint_analyzed
    ├── routing_decision
    └── ticket_info

Container: teams
├── Partition Key: /team_name
└── Documents:
    └── team_info (para RAG)

Container: audit_log
├── Partition Key: /date
└── Documents:
    └── processing_events
```

## 6. Segurança e Conformidade

### 6.1 LGPD

- **Minimização**: Apenas dados necessários são processados
- **Anonimização**: PII mascarado antes de enviar ao LLM
- **Auditoria**: Logs de todas as operações
- **Retenção**: Política de exclusão após período definido

### 6.2 Segurança Azure

- **Managed Identity**: Sem credenciais hardcoded
- **Key Vault**: Secrets centralizados
- **Private Endpoints**: Comunicação interna segura
- **RBAC**: Controle de acesso granular

## 7. Observabilidade

### 7.1 LangSmith

```python
from langsmith import Client

# Tracing automático
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "reclamaai"
```

**Métricas rastreadas:**
- Latência de cada chamada LLM
- Tokens de input/output
- Custo estimado
- Erros e exceções

### 7.2 Azure Monitor

```python
from azure.monitor.opentelemetry import configure_azure_monitor

configure_azure_monitor(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
)
```

**Dashboards:**
- Taxa de processamento
- Distribuição por categoria
- SLA de resposta
- Erros por agente

## 8. Escalabilidade

### 8.1 Estratégia de Scaling

| Componente | Estratégia |
|------------|------------|
| API | Horizontal (replicas) |
| Agentes | Async/concurrent processing |
| Cosmos DB | Serverless (auto-scale) |
| Azure AI Search | Particionamento |

### 8.2 Rate Limiting

- Azure OpenAI: Respeitar TPM/RPM limits
- Retry com exponential backoff
- Circuit breaker para serviços externos

## 9. Próximos Passos (Roadmap Técnico)

### MVP
1. Implementar Agente Coletor
2. Implementar Agente Analista
3. Implementar Agente Roteador
4. Implementar Agente Comunicador
5. Orquestração básica com LangGraph
6. API FastAPI
7. Integração Azure OpenAI
8. Integração Azure AI Search
9. Deploy local com Docker

### Fase 2
1. Agente Privacy (LGPD)
2. Agente Monitor
3. Cosmos DB integration
4. Deploy Azure Container Apps
5. CI/CD com GitHub Actions

### Fase 3
1. Agente de Aprendizado
2. Dashboard de métricas
3. A/B testing de prompts
4. Otimização de custos
