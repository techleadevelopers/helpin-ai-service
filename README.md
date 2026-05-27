# <img src="https://res.cloudinary.com/limpeja/image/upload/v1779071066/Gemini_Generated_Image_v5ufmcv5ufmcv5uf-removebg-preview_lcxvg8.png" alt="ZooHelp Logo" width="58" align="center"> Helpin Platform - AI Services

Servicos auxiliares para IA e automacao. Nao devem virar API publica principal.

Responsabilidades:
- moderacao de imagens
- NLP e classificacao de conteudo
- recomendacoes avancadas
- analytics e dashboards internos
- modelos antifraude experimentais
- scripts admin

Rodar localmente:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

## Deploy em cloud

O worker deve ser publicado no mesmo projeto cloud do backend, mas como servico
separado da API Rust. O container da API atual executa apenas
`zoohelp-backend`; adicionar os arquivos Python ao repositorio nao inicia um
segundo processo nesse servico.

Configuracao recomendada para Railway:

- criar um novo servico a partir do mesmo repositorio GitHub;
- definir o root directory como `python-workers`;
- usar o `Dockerfile` desta pasta;
- gerar um dominio interno ou publico para o worker;
- configurar `AI_WORKER_URL` no servico Rust com a URL do worker.

Health check:

```text
/healthz
```

## Plano de integracao IA para resgates

Objetivo: usar IA para aumentar velocidade, seguranca e coordenacao dos
resgates sem transformar o app em um chatbot ou poluir a interface. A IA deve
organizar informacao e sugerir proximas acoes; a decisao final continua sendo
humana.

Fluxo recomendado:

```text
Mobile/Admin -> API Rust -> Python Worker IA -> API Rust -> Mobile/Admin
```

O app mobile nao deve chamar provedor de IA diretamente. A API Rust deve
autenticar, montar o contexto minimo, chamar este worker, persistir resultado e
devolver apenas o necessario para a UX.

### 1. Antes da publicacao

Uso: melhorar a qualidade do caso sem bloquear o usuario.

Endpoint proposto:

```text
POST /ai/post-assessment
```

Entrada:

```json
{
  "description": "Cachorro atropelado na avenida...",
  "location": "Campinas, SP",
  "images": ["https://..."],
  "declaredType": "emergency"
}
```

Saida:

```json
{
  "suggestedType": "emergency",
  "urgency": "high",
  "riskLevel": "medium",
  "missingInfo": ["estado do animal", "referencia exata do local"],
  "suggestedText": "Cao ferido proximo ao numero...",
  "warnings": ["Nao informe dados pessoais sensiveis no texto publico."]
}
```

UX mobile:
- botao discreto `Analisar publicacao`;
- nunca bloquear a publicacao;
- mostrar no maximo 2 ou 3 sugestoes claras.

### 2. Durante o resgate

Este deve ser o primeiro modulo de producao, porque tem maior impacto
operacional. A IA funciona como um copiloto de resgate, nao como conversa livre.

Endpoint proposto:

```text
POST /ai/rescue-brief
```

Entrada:

```json
{
  "rescueId": "uuid",
  "post": {},
  "location": {},
  "volunteersGoing": 2,
  "chatMessages": [],
  "incidents": [],
  "lastUpdateAt": "2026-05-27T12:00:00Z"
}
```

Saida:

```json
{
  "summary": "Cao ferido em via publica, localizacao confirmada.",
  "nextAction": "Confirmar chegada de um voluntario e acionar ONG proxima.",
  "risk": "high",
  "checklist": [
    "Levar caixa de transporte",
    "Evitar aproximacao brusca",
    "Registrar foto ao chegar"
  ],
  "staleAlert": false
}
```

UX mobile/admin:
- bloco pequeno chamado `Assistente de Resgate`;
- exibir apenas `Resumo`, `Proxima acao` e `Risco`;
- checklist pode ficar recolhido;
- nao exibir texto longo automaticamente.

### 3. Depois do resgate

Uso: gerar transparencia, historico e material revisavel pela ONG/admin.

Endpoint proposto:

```text
POST /ai/final-rescue-report
```

Entrada:

```json
{
  "rescueId": "uuid",
  "post": {},
  "events": [],
  "incidents": [],
  "chatHighlights": [],
  "attachments": []
}
```

Saida:

```json
{
  "statusSuggestion": "rescued",
  "timeline": [
    { "time": "14:02", "event": "Caso publicado" },
    { "time": "14:07", "event": "Voluntario confirmou ida" }
  ],
  "finalSummary": "Animal resgatado e encaminhado para atendimento.",
  "publicUpdate": "Atualizacao: o animal foi resgatado e esta recebendo cuidado.",
  "adminNotes": "Caso teve resposta em 12 minutos. Localizacao confirmada."
}
```

UX:
- ONG revisa antes de publicar qualquer atualizacao;
- admin ve o relatorio completo;
- usuario final ve somente atualizacao publica enxuta.

### Relatorio final de resgate

O relatorio final deve ser simples para a ONG, mas robusto para auditoria. A
IA gera um rascunho; a ONG ou admin aprova, edita ou rejeita.

Versao minima obrigatoria:

```ts
type RescueStatus =
  | "rescued"      // animal salvo/localizado e em seguranca
  | "not_found"    // busca concluida sem localizar o animal
  | "died"         // animal encontrado sem vida
  | "referred"     // caso encaminhado para ONG, clinica, tutor ou outro responsavel
  | "cancelled"    // chamado cancelado antes da conclusao
  | "false_alarm"; // emergencia reportada nao existia ou nao se confirmou

type ReportPublicationStatus =
  | "draft"
  | "pending_approval"
  | "published"
  | "rejected";

type ReportRejectionReason =
  | "wrong_status"
  | "inaccurate_summary"
  | "contains_errors"
  | "other";

type RescueFinalReport = {
  rescueId: string;
  postId: string;

  status: RescueStatus;

  // 1-2 frases, linguagem operacional.
  summary: string;

  // 1 frase para usuarios finais. Pode ser igual ao summary se estiver limpa.
  publicUpdate: string;

  generatedByAi: boolean;
  approvedBy?: string; // userId da ONG ou admin
  approvedAt?: string; // ISO timestamp

  publicationStatus: ReportPublicationStatus;
  rejectionReason?: ReportRejectionReason;

  // Controle explicito para evolucao futura do schema.
  version: 1 | 2;
  schemaVersion: "1.0.0";

  createdAt: string; // ISO timestamp
  updatedAt?: string;
};
```

Exemplo minimo:

```json
{
  "rescueId": "rescue_123",
  "postId": "post_456",
  "status": "rescued",
  "summary": "Cao ferido foi localizado, resgatado e encaminhado para atendimento veterinario.",
  "publicUpdate": "Atualizacao: o animal foi resgatado e esta recebendo cuidados.",
  "generatedByAi": true,
  "publicationStatus": "pending_approval",
  "version": 1,
  "schemaVersion": "1.0.0",
  "createdAt": "2026-05-27T15:38:00Z"
}
```

Campos opcionais para a versao completa:

```ts
type RescueFinalReportFull = RescueFinalReport & {
  timeline?: Array<{
    time: string;
    event: string;
    actorType?: "user" | "ong" | "system" | "ai";
  }>;

  responseMetrics?: {
    firstResponseMinutes?: number;
    volunteersConfirmed?: number;
    incidentsReported?: number;
    chatMessagesCount?: number;
  };

  aiNotes?: {
    riskAtStart?: "low" | "medium" | "high";
    riskAtEnd?: "low" | "medium" | "high";
    importantSignals?: string[];
    suggestedFollowUp?: string;
  };

  adminNotes?: string;
};
```

Fluxo de estado:

```text
Resgate encerrado
       |
       v
IA gera rascunho (publicationStatus = draft)
       |
       v
API Rust marca como pending_approval e notifica ONG
       |
       v
ONG revisa tela de aprovacao
       |
   +---+---+
   |       |
   v       v
Aprova   Rejeita/Edita
   |       |
   v       v
published draft/rejected
```

Regras de exibicao:
- usuario final ve apenas `status` e `publicUpdate`;
- ONG ve `status`, `summary`, `publicUpdate` e pode editar antes de publicar;
- admin ve timeline, metricas, notas de IA, custo, latencia e historico.

#### Prompt fixo para geracao do relatorio final

O prompt deve ser versionado junto do schema. Alteracoes relevantes devem
incrementar `schemaVersion` ou `promptVersion`.

```markdown
## System Prompt - Rescue Final Report Generation

You are an operational assistant for Helpin, a rescue coordination platform.

### Input Data
You will receive:
- Original post (description, location, images metadata)
- Rescue timeline (events with timestamps)
- Volunteer count
- Incident reports
- Chat message summary (if available)

### Output Requirements (STRICT)

Generate a JSON object with:

1. `statusSuggestion`: One of ["rescued", "not_found", "died", "referred", "cancelled", "false_alarm"]
   - "rescued" = animal was found and is now safe
   - "not_found" = search concluded without locating the animal
   - "died" = animal was found deceased
   - "referred" = case transferred to another organization
   - "cancelled" = rescue was called off before completion
   - "false_alarm" = reported emergency did not exist

2. `summary`: EXACTLY 1-2 sentences, operational language, third person past tense
   - Example: "Cao foi localizado na Rua das Flores e encaminhado para Clinica Veterinaria Solidaria."

3. `publicUpdate`: EXACTLY 1 sentence, user-friendly language, first-person or neutral
   - Example: "Atualizacao: o animal foi resgatado e esta recebendo cuidados."

### Rules
- DO NOT include specific addresses or personal contact information
- DO NOT make medical diagnoses
- DO NOT guarantee outcomes (e.g., "will survive")
- DO NOT blame volunteers, victims, or third parties
- If confidence is low (<70%), set `confidence: "low"` in metadata

### Output Format
Return ONLY valid JSON. No markdown, no explanation.
```

#### Endpoints recomendados na API Rust

O worker Python pode expor endpoints internos `/ai/*`, mas os endpoints
publicos/autenticados devem ficar na API Rust.

```text
POST /v1/rescue/:rescueId/generate-report
```

Gera rascunho automaticamente ao encerrar resgate ou sob demanda.

```json
{
  "reportId": "report_789",
  "statusSuggestion": "rescued",
  "summary": "Cao foi localizado e encaminhado para atendimento.",
  "publicUpdate": "Atualizacao: o animal foi resgatado e esta recebendo cuidados."
}
```

```text
GET /v1/rescue/:rescueId/report/draft
```

ONG visualiza o rascunho pendente.

```text
POST /v1/rescue/:rescueId/report/publish
```

ONG aprova e pode editar antes de publicar.

```json
{
  "status": "rescued",
  "summary": "Texto editado opcional",
  "publicUpdate": "Texto publico opcional"
}
```

```text
GET /v1/posts/:postId/rescue-report
```

Busca relatorio publicado para exibicao publica.

```text
GET /v1/admin/reports?status=pending&limit=50
```

Admin consulta fila e historico de relatorios.

#### Tabela recomendada

```sql
CREATE TABLE rescue_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rescue_id UUID NOT NULL REFERENCES rescues(id),
  post_id UUID NOT NULL REFERENCES posts(id),

  status VARCHAR(20) NOT NULL,
  summary TEXT NOT NULL,
  public_update TEXT NOT NULL,

  generated_by_ai BOOLEAN DEFAULT false,
  ai_model VARCHAR(50),
  ai_confidence FLOAT,
  ai_latency_ms INTEGER,
  ai_cost_cents INTEGER,

  publication_status VARCHAR(20) DEFAULT 'draft',
  approved_by UUID REFERENCES users(id),
  approved_at TIMESTAMP,
  rejection_reason TEXT,

  timeline JSONB,
  response_metrics JSONB,
  ai_notes JSONB,
  admin_notes TEXT,

  version INTEGER DEFAULT 1,
  schema_version VARCHAR(10) DEFAULT '1.0.0',

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_reports_rescue_id ON rescue_reports(rescue_id);
CREATE INDEX idx_reports_post_id ON rescue_reports(post_id);
CREATE INDEX idx_reports_status ON rescue_reports(publication_status);
CREATE INDEX idx_reports_approved_at ON rescue_reports(approved_at);
```

#### Regras de negocio

Validacoes obrigatorias:

```ts
const VALIDATION_RULES = {
  summary: {
    maxLength: 280,
    required: true,
    noPII: true,
    noDiagnosis: true,
  },
  publicUpdate: {
    maxLength: 140,
    required: true,
    familyFriendly: true,
  },
  status: {
    allowed: ["rescued", "not_found", "died", "referred", "cancelled", "false_alarm"],
  },
};
```

Politica de retry:

```ts
const RETRY_CONFIG = {
  maxAttempts: 3,
  backoffMs: [1000, 2000, 4000],
  fallbackToTemplate: true,
};
```

Fallback se a IA falhar:

```json
{
  "status": "referred",
  "summary": "Caso encerrado pela equipe responsavel. Detalhes aguardam revisao.",
  "publicUpdate": "Atualizacao: o caso foi encerrado pela equipe responsavel.",
  "generatedByAi": false,
  "publicationStatus": "pending_approval"
}
```

#### UI de aprovacao para ONG

```text
+-------------------------------------------------------------+
|  Resgate concluido - Pendente de relatorio                  |
+-------------------------------------------------------------+
|                                                             |
|  Status sugerido pela IA:                                   |
|  o Resgatado     o Nao encontrado     o Falso alarme        |
|  x Encaminhado   o Cancelado          o Falecido            |
|                                                             |
|  Resumo editavel:                                           |
|  +-------------------------------------------------------+  |
|  | Cao foi localizado na regiao informada e encaminhado  |  |
|  | para atendimento responsavel.                         |  |
|  +-------------------------------------------------------+  |
|                                                             |
|  Atualizacao publica editavel:                             |
|  +-------------------------------------------------------+  |
|  | Atualizacao: o animal foi resgatado e esta recebendo  |  |
|  | cuidados.                                             |  |
|  +-------------------------------------------------------+  |
|                                                             |
|  [Cancelar]                          [Aprovar e publicar]  |
+-------------------------------------------------------------+
```

#### Custos e limites

Adicionar em `ai_assessments` e/ou `rescue_reports`:

```text
ai_latency_ms
ai_cost_cents
ai_model
prompt_version
```

Politica de produto:
- plano gratuito: classificacao basica e relatorio simples;
- plano premium ONG: assistente durante resgate, risco avancado, relatorio
  detalhado e auditoria expandida;
- admin deve enxergar custo por chamada, latencia media e taxa de rejeicao.

## Persistencia esperada na API Rust

Este worker deve retornar sugestoes. A API Rust deve persistir os resultados em
tabelas auditaveis.

Tabelas recomendadas:

```text
ai_assessments
- id
- post_id
- rescue_id
- type: post_assessment | rescue_brief | final_report
- input_hash
- output_json
- model
- confidence
- reviewed_by_user
- accepted
- created_at

rescue_events
- id
- rescue_id
- type
- actor_id
- message
- metadata
- created_at

rescue_reports
- id
- rescue_id
- summary
- public_update
- final_status
- ai_generated
- approved_by
- created_at
```

## Regras de seguranca e produto

Obrigatorio:
- IA sempre como sugestao;
- humano confirma decisao final;
- salvar input resumido e output para auditoria;
- remover ou mascarar dados sensiveis antes de enviar ao provedor;
- nao diagnosticar doencas;
- nao prometer chegada de ajuda;
- nao exibir score cru sem explicacao;
- permitir fallback sem IA.

Texto correto:

```text
Risco alto sugerido pela analise do caso.
```

Texto proibido:

```text
A IA confirmou emergencia real.
```

## Ordem de implementacao

1. Criar `rescue_events` na API Rust.
2. Criar endpoint Rust que chama `POST /ai/rescue-brief`.
3. Exibir `Assistente de Resgate` no mobile e admin.
4. Criar `POST /ai/final-rescue-report`.
5. Persistir e revisar `rescue_reports`.
6. Adicionar `POST /ai/post-assessment` na publicacao.

Frase guia do produto:

```text
A IA organiza o resgate. Pessoas tomam a decisao.
```
