# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ReclamaAI is a multi-agent system for automated complaint management in e-commerce. It uses LangGraph for orchestration, Azure OpenAI for LLM analysis, and Azure AI Search for RAG-based routing.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server (development)
uvicorn src.api.main:app --reload --port 8000

# Run with Docker
docker-compose up -d

# Run all tests
pytest tests/ -v

# Run single test file
pytest tests/unit/test_file.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Lint and format
black src/ tests/
isort src/ tests/
flake8 src/ tests/ --max-line-length=100
```

## Architecture

### Multi-Agent Workflow (LangGraph)

The system processes complaints through a state machine with these stages:
```
NEW → ANONYMIZED → ANALYZED → ROUTED → TICKET_CREATED → NOTIFIED → COMPLETED
```

**Agents** (in `src/agents/`):
- **Coletor**: Ingests complaints from multiple mock sources (Reclame Aqui, Jira, Chat, Email, Phone)
- **Privacy**: Masks PII for LGPD compliance before LLM processing
- **Analista**: Uses Azure OpenAI to classify, summarize, extract sentiment/urgency
- **Roteador**: Uses RAG with Azure AI Search to route to the correct team
- **Comunicador**: Creates Jira tickets and sends email notifications (mocked)
- **Monitor**: Collects observability metrics

### Communication Pattern (A2A)

Agents communicate via shared `ComplaintState` in LangGraph. Each agent receives the state, processes it, and returns an updated state.

### Key Data Models (`src/models/schemas.py`)

- `ComplaintRaw`: Normalized complaint from any source
- `ComplaintAnalyzed`: LLM analysis output (summary, category, sentiment, urgency)
- `RoutingDecision`: Team assignment with SLA and priority
- `ComplaintState`: Full workflow state passed between agents

### Teams for Routing

| Team | Categories |
|------|------------|
| Logística | Delivery delays, lost packages |
| Financeiro | Billing, refunds, chargebacks |
| Produtos | Defects, wrong items, warranty |
| Atendimento N2 | Escalations, PROCON threats |
| Marketplace | Third-party seller issues |

## Configuration

Settings in `src/core/config.py` use pydantic-settings. Required environment variables:
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`
- `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`
- `COSMOS_ENDPOINT`, `COSMOS_KEY`
- `LANGCHAIN_API_KEY`

Copy `.env.example` to `.env` and fill in credentials.

## Mock Data

Located in `data/mock/`:
- `reclame_aqui.json`: 40 complaints
- `jira_issues.json`: 20 issues
- `chat_transcripts.json`: 15 chat/WhatsApp transcripts
- `phone_transcripts.json`: 10 phone call transcripts
- `support_emails.json`: 20 support emails
- `teams.json`: Team definitions for RAG routing

## Complaint Categories

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
