# Vitarerum

Vitarerum is a modular application for museum collection-use workflows,
including proposal intake, collection-use projects, public questions, in-situ
visit records, CIDOC-CRM mapping, reports, and AI-assisted narrative/triage
features.

This repository contains the backend API, the Angular frontend, and shared
documentation.

## Projects

- [Backend API](./vitarerum-api/README.md)
- [Frontend UI](./vitarerum-ui/README.md)

## Documentation

- [Architecture overview](./docs/architecture/README.md)
- [Context map](./docs/architecture/context-map.puml)
- [Module boundaries](./docs/architecture/module-boundaries.md)
- [Business flows](./docs/architecture/business-flows.md)
- [Architecture decisions](./docs/architecture/adr/README.md)
- [API contracts](./docs/api_contracts/)
- [Diagrams](./docs/diagrams/)
- [Cloud deployment plan](./docs/cloud/README.md)

## Notes

The backend is a modular monolith. Cross-context communication is synchronous
through published-language modules and narrow ACLs, with dependency rules
enforced by import-linter contracts.

Detailed setup, runtime configuration, and commands live in the subproject
READMEs linked above.

