# ZooHelp Python Workers

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
