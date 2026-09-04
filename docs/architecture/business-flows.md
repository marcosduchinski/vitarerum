---
status: current
---

# Business Flows

This is an index of end-to-end business flows, the diagrams that draw them and
the specifications that state their rules. When a flow is not yet diagrammed,
this file records the gap without inventing an incomplete diagram.

Endpoint-level HTTP documentation is the generated OpenAPI schema; what is
shared by every endpoint is in the
[cross-cutting contract](../api_contracts/README.md).

## Proposal Intake and Lifecycle

- Public proposal submission:
  [SPEC-010](../specs/010-submissao-publica/spec.md).

![Public submission double opt-in](../diagrams/public-submission-double-opt-in.svg)

![Public proposal lifecycle](../diagrams/public-proposal-life-cycle.svg)

- Authenticated proposal submission:
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md).
- Proposal origin identification: documented by
  [ADR 0001](./adr/0001-submission-channel.md).
- Proposal lifecycle:
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md).

![Proposal lifecycle](../diagrams/proposal-life-cycle.svg)

- Document correction and attachments: covered by
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md) and the public
  submission/amendment states above.
- Staff notifications triggered by proposal events:

![Notifications flow](../diagrams/notifications-flow.svg)

## Collection Use Projects

- Project lifecycle:
  [SPEC-009](../specs/009-projeto-uso-de-colecoes/spec.md).

![Use of collections lifecycle](../diagrams/use-of-collections-life-cycle.svg)

- Object search and requested-object snapshots:
  [SPEC-014](../specs/014-catalogo-e-indice-de-objetos/spec.md).
  A dedicated end-to-end diagram for object selection is still to document.
- Reference number policy administration:

![Reference number policies](../diagrams/reference-number-policies.svg)

## In-Situ Visit, CIDOC-CRM, and Narrative

- In-situ visit to CIDOC/narrative flow:

![In-situ visit CIDOC narrative flow](../diagrams/in-situ-visit-cidoc-narrative-flow.svg)

- In-situ visit context map:

![In-situ visit context map](../diagrams/in-situ-visit-context-map.svg)

- CIDOC-CRM mapping:
  [SPEC-013](../specs/013-mapeamento-cidoc-crm/spec.md).

![CIDOC-CRM in-situ visit record model](../diagrams/cidoc-crm-in-situ-visit-record-model.svg)

![CIDOC example in-situ visit](../diagrams/cidoc-example-in-situ-visit.svg)

- Narrative generation:
  [SPEC-017](../specs/017-narrativa-museologica/spec.md).
- Report aggregation:
  [SPEC-015](../specs/015-relatorio-visita-in-situ/spec.md).
- External publication of reports and JSON-LD:

![External publications flow](../diagrams/external-publications-flow.svg)

## Scientific Return

The largest flow in the system, and the newest. Rules and invariants live in
[SPEC-001](../specs/001-investigacao-agentica-assistida/spec.md) through
[SPEC-006](../specs/006-avaliacao-retorno-cientifico/spec.md),
[SPEC-024](../specs/024-investigacao-agentica-autonoma/spec.md) and
[SPEC-025](../specs/025-base-de-conhecimento-curatorial/spec.md); the reading
order is in the [specifications index](../specs/README.md).

- Coexisting flows and the full-agentic cycle:

![Scientific return flows](../diagrams/scientific-return-flow.svg)

- The exclusively autonomous cycle:

![Scientific return full-agentic flow](../diagrams/scientific-return-full-agentic-flow.svg)

- Autonomous search, from trigger to curatorial decision:

```mermaid
%% source: ../diagrams/flow-autonomous-search.mmd
flowchart TD
    SEARCH_NOW["Search now"]:::gray
    START_AGENT["Start autonomous search"]:::gray
    SCHEDULE["Data programada alcançada"]:::gray

    ACTIVE{"Monitorização ativa?"}:::dec
    STOP["Nenhuma pesquisa executada"]:::gray

    RULES["Pesquisa por regras sobre o snapshot do projeto:<br/>inventário, autor+inventário, inventário+objeto e autor+objeto"]:::blue
    ACTIONABLE{"O resultado liga-se ao objeto<br/>ou ao investigador?"}:::dec
    DISCARD["Resultado descartado"]:::gray
    CANDIDATE_RULES["Candidato pendente"]:::blue

    QUEUE_AI["Investigação autónoma em fila, executada em segundo plano"]:::viol
    MEMORY["Carrega o snapshot e o conhecimento curatorial ativo"]:::gray
    FLOOR["Pesquisa inicial garantida: apelido + objeto<br/>e número de inventário sem prefixo"]:::blue
    READ["IA analisa cada publicação separadamente"]:::viol
    RELEVANT{"Publicação relevante?"}:::dec
    CANDIDATE_AI["Cria ou reutiliza candidato pendente"]:::blue
    CONTINUE{"Continuar?"}:::dec
    PLAN["IA prepara novas pesquisas e escolhe as fontes"]:::viol
    FINISH["Investigação concluída"]:::viol

    REVIEW["Fila de revisão humana"]:::green
    DECISION{"Decisão do curador"}:::dec
    PENDING["Continua pendente"]:::gray
    DISMISSED["Candidato rejeitado"]:::red
    PUBLICATION["Registo de publicação criado no Projeto"]:::green
    LEARN["A justificação do curador é convertida pela IA numa lição proposta"]:::viol
    ACTIVATE["Curador ativa a lição"]:::green

    SEARCH_NOW --> ACTIVE
    SCHEDULE --> ACTIVE
    START_AGENT --> ACTIVE
    ACTIVE -->|Não| STOP
    ACTIVE -->|"Sim: Search now ou data programada"| RULES
    ACTIVE -->|"Sim: Start autonomous search"| QUEUE_AI

    RULES --> ACTIONABLE
    ACTIONABLE -->|Não| DISCARD
    ACTIONABLE -->|Sim| CANDIDATE_RULES
    CANDIDATE_RULES --> REVIEW

    QUEUE_AI --> MEMORY
    MEMORY --> FLOOR
    FLOOR --> READ
    READ --> RELEVANT
    RELEVANT -->|"Não, descartada"| CONTINUE
    RELEVANT -->|Sim| CANDIDATE_AI
    CANDIDATE_AI --> REVIEW
    CANDIDATE_AI --> CONTINUE
    CONTINUE -->|"Sim, dentro dos limites"| PLAN
    PLAN --> READ
    CONTINUE -->|"Não: limite atingido ou a IA decidiu parar"| FINISH
    FINISH -.->|"Segue para revisao humana"| REVIEW

    REVIEW --> DECISION
    DECISION -->|"Decidir mais tarde"| PENDING
    DECISION -->|"Rejeitar, com nota obrigatória"| DISMISSED
    DECISION -->|"Confirmar, sem nota"| PUBLICATION
    DECISION -->|"Corrigir e confirmar, com nota opcional"| PUBLICATION
    DISMISSED -.-> LEARN
    PUBLICATION -.->|"só a partir de corrigir e confirmar,<br/>e só se a nota for preenchida"| LEARN
    LEARN --> ACTIVATE
    ACTIVATE -.->|"usada nas investigações seguintes"| MEMORY

    REFRESH["O painel só mostra o progresso depois de Refresh"]:::gray
    REFRESH -.-> QUEUE_AI

    LIMITS["Limites padrão por investigação: 4 ciclos, 12 pesquisas,<br/>40 resultados, 5 candidatos e 20 chamadas à IA"]:::gray
    LIMITS -.-> CONTINUE

    classDef blue fill:#E6F1FB,color:#0C447C,stroke:#378ADD,stroke-width:0.5px;
    classDef viol fill:#EEEDFE,color:#3C3489,stroke:#7F77DD,stroke-width:0.5px;
    classDef green fill:#EAF3DE,color:#27500A,stroke:#639922,stroke-width:0.5px;
    classDef gray fill:#F1EFE8,color:#444441,stroke:#888780,stroke-width:0.5px;
    classDef red fill:#FCEBEB,color:#791F1F,stroke:#E24B4A,stroke-width:0.5px;
    classDef dec fill:none,color:#3d3d3a,stroke:#73726c,stroke-width:0.5px;
```

## Museum Questions

- Public question submission:
  [SPEC-011](../specs/011-perguntas-ao-museu/spec.md).

![Museum questions public flow](../diagrams/museum-questions-public-flow.svg)

- Staff response: same spec, staff-facing requirements.

![Museum questions response flow](../diagrams/museum-questions-response-flow.svg)

## Administration

- Document templates:
  [SPEC-012](../specs/012-modelos-de-documento/spec.md).
- Collection data sources and catalog administration:
  [SPEC-014](../specs/014-catalogo-e-indice-de-objetos/spec.md).
- AI prompts:
  [SPEC-016](../specs/016-prompts-versionados/spec.md).

![AI prompts lifecycle](../diagrams/ai-prompts-life-cycle.svg)

- Dashboard summary: the `/p/dashboard` page is served by existing list
  endpoints. Dedicated summary endpoints are proposed but not implemented -
  see [Dashboard Summary API (proposed)](../proposals/17Dashboard-Summary-API.md)
  and [SPEC-021](../specs/021-resumos-de-painel/spec.md).

![Dashboard summary flow](../diagrams/dashboard-summary-flow.svg)

- External publication administration:

![External publication administration](../diagrams/external-publications-flow.svg)
