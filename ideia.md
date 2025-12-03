Plataforma de Gestão Automática de Reclamações com Arquitetura Multiagente (Reclame Aqui → Jira + E-mail) – COM SIMULAÇÃO DE DADOS
1. Contexto e Objetivo

Quero desenvolver um sistema multiagente em Python que automatize o fluxo de tratamento de reclamações de uma empresa fictícia, unificando dados provenientes de múltiplas fontes como Reclame Aqui, Jira, canais de atendimento (chat, telefone, WhatsApp), e emails de suporte. Este sistema será responsável por:

Buscar reclamações usando dados simulados de múltiplas fontes.

Usar LLM para entender o problema, resumir e classificar.

Roteamento inteligente para a área correta usando RAG (Vector DB / Azure AI Search ou similar).

Criar automaticamente tickets no Jira e enviar notificações por e-mail.

Implementar monitoramento, tolerância a falhas, segurança (LGPD) e espaço para aprendizado contínuo.

2. Visão Geral da Arquitetura

Arquitetura baseada em Sistema Multiagente (SMA) com:

Orquestrador central (Manager Agent / Workflow Engine).

Agentes especializados, cada um com responsabilidades bem definidas.

API principal em FastAPI.

Uso de framework multiagente/fluxo (LangGraph ou crewAI) para orquestrar os agentes.

Integração com:

Mock da API Reclame Aqui (dados locais simulados),

Mock de dados de problemas no Jira,

Mock de chats de atendimento,

Mock de emails de suporte,

API Jira para criação de tickets,

Serviço de e-mail (SMTP, Gmail API ou equivalente corporativo).

Deploy em containers (Docker), com potencial para rodar em Azure Container Apps, Kubernetes ou App Service.

3. Papéis dos Agentes
3.1. Agente Coletor (Perception / Ingestion Agent)

Responsabilidade: Ingerir reclamações de múltiplas fontes de dados simuladas.

Fontes de dados (IMPORTANTE):

API de Mock do Reclame Aqui: Carga de 200 reclamações de uma empresa fictícia.

Mock de Problemas no Jira: Reclamações e problemas registrados no Jira com status, categoria, e descrição.

Canais de Atendimento (Mock): Dados de reclamações registradas via chat (WhatsApp, chat online) ou telefone (com transcrição simulada).

Emails de Suporte: Reclamações registradas via emails de clientes para o time de suporte.

Ações:

Ler dados de várias fontes:

Reclame Aqui (API Mock),

Jira (problemas criados),

Atendimentos (chat, telefone, e-mails),

Normalizar os dados no formato ComplaintRaw (semelhante a uma reclamação) e unificar:

{
  "external_id": "RA-123456",
  "source": "reclame_aqui", 
  "company_name": "TechNova Store",
  "title": "Produto chegou com a tela quebrada",
  "description": "Comprei um celular no dia 05/10 e ele chegou com a tela trincada...",
  "consumer_name": "João S.",
  "created_at": "2025-10-10T14:32:00Z",
  "channel": "Reclame Aqui",
  "city": "São Paulo",
  "state": "SP",
  "product_category": "Smartphone",
  "status": "Não Respondida"
}


Verificar se a reclamação já foi processada consultando o banco interno.

Saída:

Lista de reclamações novas normalizadas para o Orquestrador.

3.2. Agente Analista (LLM Agent)

Responsabilidade: Entender o texto da reclamação usando LLM.

Entrada:

ComplaintRaw com título, descrição e metadados.

Ações (via LLM):

Gerar um resumo curto e objetivo do problema.

Classificar a reclamação em uma categoria de negócio (ex: “Problema no frete”, “Cobrança indevida”, “Produto com defeito”).

Extrair sentimento / tom (neutro, insatisfeito, muito insatisfeito).

Estimar urgência (baixa, média, alta, crítica) com base em palavras-chave e contexto (prazo, PROCON, processo, saúde, etc.).

Saída:

Objeto ComplaintAnalyzed com:

resumo,

categoria,

sentimento,

urgência,

campos brutos originais.

3.3. Agente de Qualidade (QA Agent)

Responsabilidade: Validar o trabalho do Agente Analista antes de seguir.

Entrada:

ComplaintAnalyzed.

Ações:

Validar consistência entre resumo, categoria e texto original.

Usar RAG + regras:

exemplo: se urgência = “alta”, mas o texto não menciona nada crítico, levantar suspeita.

Em caso de dúvida:

Solicitar reprocessamento ao Analista com prompt mais estruturado.

Ou marcar reclamação para revisão humana.

Saída:

ComplaintAnalyzed marcado como “aprovado” ou “necessita revisão humana”.

3.4. Agente Roteador (Routing / Knowledge Agent)

Responsabilidade: Decidir para qual área/time e qual prioridade mandar a reclamação.

Entrada:

ComplaintAnalyzed aprovado.

Ferramentas:

RAG / Vector DB (ou Azure AI Search) com:

Descrição das áreas e times,

Responsabilidades,

Contatos,

Exemplos de casos históricos.

Regras de negócio (SLA, níveis de prioridade, etc.).

Ações:

Fazer busca semântica no Vector DB usando resumo + categoria + sentimento.

Receber top N áreas mais parecidas (ex: “Time de Logística”, “Financeiro – Cobrança”).

Selecionar área responsável mais adequada.

Definir prioridade do ticket (ex: baseado em urgência + tipo + histórico).

Saída:

Objeto RoutingDecision com:

área/time,

responsável (nome/e-mail),

prioridade,

justificativa textual.

3.5. Agente Comunicador (Action / Notifier Agent)

Responsabilidade: Executar ações nos sistemas externos (Jira e e-mail).

Entrada:

ComplaintAnalyzed,

RoutingDecision.

Ações:

Criar ticket no Jira:

título padronizado,

descrição contendo:

resumo,

texto original (ou parte dele),

categoria,

urgência,

área direcionada,

link para a reclamação.

Definir prioridade conforme decisão.

Salvar no banco interno o vínculo: id_reclame_aqui ↔ id_ticket_jira.

Enviar e-mail para o responsável:

Informando o novo ticket,

Link direto do ticket,

Resumo do problema.

Saída:

TicketInfo (id_jira, link, status_criação).

3.6. Agente de Compliance / Segurança (Privacy Agent)

Responsabilidade: Proteger dados sensíveis (LGPD).

Entrada:

ComplaintRaw e campos de saída.

Ações:

Detectar e mascarar informações sensíveis antes de mandar para a LLM:

CPF, e-mail, telefone, endereço, cartão, etc.

Manter mapeamento interno entre texto original e versão mascarada.

Garantir que logs, prompts e contexto de RAG não guardem dados sensíveis em claro.

Saída:

Versões seguras de texto para uso com LLMs e logs.

3.7. Agente de Monitoramento (Observability Agent)

Responsabilidade: Monitorar a saúde e desempenho do sistema.

Entrada:

Métricas de todos os agentes.

Ações:

Coletar:

número de reclamações processadas,

taxa de erro por agente,

latência média de chamadas externas.

Gerar logs estruturados.

Enviar alertas quando:

Fila de reclamações pendentes exceder limite,

Algum serviço externo estiver falhando demais,

Tempo médio de processamento estiver muito alto.

3.8. Agente de Feedback / Aprendizado Contínuo (Learning Agent – versão 2.0)

Responsabilidade: Aprender com o histórico do Jira.

Entrada:

Histórico do Jira:

Mudanças de área,

Alterações de prioridade,

Tempos de resolução,

Reaberturas.

Ações:

Identificar padrões e sugerir ajustes de:

Regras do Roteador,

Corpus do RAG.

Saída:

Sugestões de melhoria para regras,

Atualização dos dados do Vector DB.

4. Orquestrador (Manager / Workflow Engine)

Implementado com LangGraph, crewAI ou similar.

Modelo de máquina de estados para cada reclamação:

NEW → ANALYZED → QA_OK → ROUTED → TICKET_CREATED → NOTIFIED

Estados de erro: FAILED_LLM, FAILED_JIRA, etc.

Responsabilidades:

Garantir idempotência (não criar ticket duplicado).

Gerenciar retries com backoff (principalmente para integrações externas).

Permitir reprocessamento manual.

5. Modelo de Dados (alto nível)

complaints:

id_interno

external_id (id no Reclame Aqui – simulado)

source (reclame_aqui, jira, chat, email)

title

description_original

created_at

status_atual

campos de auditoria (created_at, updated_at, etc.)

complaints_analysis:

id_complaint

resumo

categoria

sentimento

urgência

aprovado_qa (bool)

routing_decisions:

id_complaint

area

responsavel

prioridade

justificativa

tickets:

id_complaint

id_jira

link_jira

status

6. Tecnologias e Stack

Backend/API: FastAPI (Python).

Orquestração Multiagente: LangGraph ou crewAI.

LLM: OpenAI / Azure OpenAI.

RAG / Busca Semântica:

Azure AI Search ou outro Vector DB (FAISS, Chroma, etc.).

Banco de Dados:

Postgres ou outro relacional.

Integrações:

Mock da API Reclame Aqui (JSON + endpoints simulados),

Problemas no Jira,

Canais de Suporte (WhatsApp, Chat, E-mail).

Infra/DevOps:

Docker para containerização.

CI/CD com GitHub Actions.

Deploy em Azure (Container Apps / Kubernetes / App Service).

7. Fluxo Principal (End-to-End)

Agente Coletor consome os mocks das fontes de dados (Reclame Aqui, Jira, Canais de Atendimento e Emails).

Orquestrador dispara:

Privacy Agent para anonimizar dados sensíveis.

Analista (LLM) para resumo, categoria, sentimento e urgência.

QA Agent para validação.

Após aprovação, Roteador usa RAG + regras para definir área, responsável e prioridade.

Comunicador cria ticket no Jira, registra no banco e envia e-mail ao responsável.

Monitoramento registra métricas e erros.

Versão 2.0: Learning Agent usa histórico do Jira para melhorar o sistema.

8. Seção Especial: Simulação das Fontes de Dados

Criar dados simulados para diferentes fontes:

Reclame Aqui: ~200 reclamações.

Jira: ~200 problemas com status, categoria, e descrição.

Canais de Atendimento (WhatsApp, chat, telefone): ~150 reclamações.

Emails de Suporte: ~100 e-mails com reclamações e problemas.