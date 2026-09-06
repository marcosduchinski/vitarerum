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
    SCHEDULE["Scheduled date reached"]:::gray

    ACTIVE{"Monitoring active?"}:::dec
    STOP["No search is run"]:::gray

    RULES["Rule-based search over the project snapshot:<br/>inventory, author+inventory, inventory+object and author+object"]:::blue
    ACTIONABLE{"Does the result tie back to the object<br/>or to the researcher?"}:::dec
    DISCARD["Result discarded"]:::gray
    CANDIDATE_RULES["Pending candidate"]:::blue

    QUEUE_AI["Autonomous investigation queued, run in the background<br/>one investigation per consulted object"]:::viol
    MEMORY["Loads the snapshot for its object and the active<br/>curatorial knowledge of that inventory number"]:::gray
    FLOOR["Guaranteed first searches: surname + object<br/>and the inventory number without its prefix"]:::blue
    READ["The AI reads each publication on its own"]:::viol
    RELEVANT{"Publication relevant?"}:::dec
    CANDIDATE_AI["Creates or reuses a pending candidate"]:::blue
    CONTINUE{"Continue?"}:::dec
    PLAN["The AI prepares new searches and picks the sources"]:::viol
    FINISH["Investigation finished"]:::viol
    ENRICH["Enrichment cycle over candidates with no inventory evidence"]:::viol

    REVIEW["Human review queue"]:::green
    DECISION{"Curator decision"}:::dec
    PENDING["Stays pending"]:::gray
    DISMISSED["Candidate dismissed"]:::red
    PUBLICATION["Publication entry created on the Project"]:::green
    LEARN["The curator's justification is turned by the AI into a proposed lesson"]:::viol
    ACTIVATE["The curator activates the lesson"]:::green

    SEARCH_NOW --> ACTIVE
    SCHEDULE --> ACTIVE
    START_AGENT --> ACTIVE
    ACTIVE -->|No| STOP
    ACTIVE -->|"Yes: Search now or scheduled date"| RULES
    ACTIVE -->|"Yes: Start autonomous search"| QUEUE_AI
    RULES -.->|"scheduled sweep only: one investigation<br/>per consulted object, capped at 15"| QUEUE_AI

    RULES --> ACTIONABLE
    ACTIONABLE -->|No| DISCARD
    ACTIONABLE -->|Yes| CANDIDATE_RULES
    CANDIDATE_RULES --> REVIEW

    QUEUE_AI --> MEMORY
    MEMORY --> FLOOR
    FLOOR --> READ
    READ --> RELEVANT
    RELEVANT -->|"No, discarded"| CONTINUE
    RELEVANT -->|Yes| CANDIDATE_AI
    CANDIDATE_AI --> REVIEW
    CANDIDATE_AI --> CONTINUE
    CONTINUE -->|"Yes, within the limits"| PLAN
    PLAN --> READ
    CONTINUE -->|"No: limit reached or the AI chose to stop"| FINISH
    FINISH --> ENRICH
    ENRICH -.->|"decides nothing; unproven candidates stay pending"| REVIEW
    FINISH -.->|"Goes on to human review"| REVIEW

    REVIEW --> DECISION
    DECISION -->|"Decide later"| PENDING
    DECISION -->|"Dismiss, note required"| DISMISSED
    DECISION -->|"Confirm, no note"| PUBLICATION
    DECISION -->|"Correct and confirm, note optional"| PUBLICATION
    DISMISSED -.-> LEARN
    PUBLICATION -.->|"only from correct and confirm,<br/>and only if the note was filled in"| LEARN
    LEARN --> ACTIVATE
    ACTIVATE -.->|"used in the investigations that follow"| MEMORY

    REFRESH["The panel only shows progress after Refresh"]:::gray
    REFRESH -.-> QUEUE_AI

    LIMITS["Default limits per investigation: 4 cycles, 12 searches,<br/>40 results, 5 candidates and 20 AI calls"]:::gray
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
