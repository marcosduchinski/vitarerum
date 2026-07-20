# Business Flows

This is an index of end-to-end business flows and the diagrams or contracts
that currently describe them. When a flow is not yet diagrammed, this file
records the gap without inventing an incomplete diagram.

## Proposal Intake and Lifecycle

- Public proposal submission:
  [PUBLIC_SUBMISSION.puml](../diagrams/PUBLIC_SUBMISSION.puml),
  [public-proposal-life-cicle.puml](../diagrams/public-proposal-life-cicle.puml),
  [PublicProposalSubmission API](../api_contracts/11PublicProposalSubmission-API.md).
- Authenticated proposal submission:
  [Proposal phase - researcher actions](../api_contracts/02Proposal%20phase%20%E2%80%94%20researcher%20actions.md).
- Proposal origin identification: documented by
  [ADR 0001](./adr/0001-submission-channel.md).
- Proposal lifecycle:
  [proposal-life-cicle.puml](../diagrams/proposal-life-cicle.puml),
  [Proposal phase - staff actions](../api_contracts/03Proposal%20phase%20%E2%80%94%20staff%20actions.md).
- Document correction and attachments: covered across proposal API contracts and
  the public submission/amendment flow; a dedicated flow diagram is still to
  document.

## Collection Use Projects

- Project lifecycle:
  [use-of-collections-life-cicle.puml](../diagrams/use-of-collections-life-cicle.puml),
  [Project phase - researcher actions](../api_contracts/04Project%20phase%20%E2%80%94%20researcher%20actions.md),
  [Project phase - staff actions](../api_contracts/05Project%20phase%20%E2%80%94%20staff%20actions.md).
- Object search and requested-object snapshots:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
  A dedicated end-to-end diagram for object selection is still to document.

## In-Situ Visit, CIDOC-CRM, and Narrative

- In-situ visit to CIDOC/narrative flow:
  [in-situ-visit-cidoc-narrative-flow.puml](../diagrams/in-situ-visit-cidoc-narrative-flow.puml).
- In-situ visit context map:
  [in-situ-visit-context-map.puml](../diagrams/in-situ-visit-context-map.puml).
- CIDOC-CRM mapping:
  [cidoc-crm.puml](../diagrams/cidoc-crm.puml),
  [cidoc.puml](../diagrams/cidoc.puml),
  [InSituVisit-CIDOC-CRM API](../api_contracts/08InSituVisit-CIDOC-CRM.md).
- Narrative generation:
  [KG-RAG Narrative API](../api_contracts/09KG-RAG-Narrative.md).
- Report aggregation:
  [Reports InSituVisit API](../api_contracts/10Reports-InSituVisit.md).

## Museum Questions

- Public question submission:
  [museum-questions-public-flow.puml](../diagrams/museum-questions-public-flow.puml),
  [MuseumQuestions Public API](../api_contracts/13MuseumQuestions-Public-API.md).
- Staff response:
  [museum-questions-response-flow.puml](../diagrams/museum-questions-response-flow.puml),
  [MuseumQuestions Internal API](../api_contracts/14MuseumQuestions-Internal-API.md).
- AI triage:
  covered by the triage context and related plans; a dedicated durable flow
  diagram is still to document if the implementation changes materially.

## Administration

- Document templates:
  [DocumentTemplates API](../api_contracts/12DocumentTemplates-API.md).
- Collection data sources:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
- AI prompts:
  [AI Prompts Admin API](../api_contracts/16AI-Prompts-Admin-API.md).
- Dashboard summary:
  [Dashboard Summary API](../api_contracts/17Dashboard-Summary-API.md).

