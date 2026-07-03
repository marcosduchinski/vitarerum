# Plano — Correção documental em propostas públicas (amendment flow)

> **STATUS: IMPLEMENTADO** (2026-07-03). Backend + testes concluídos; frontend (§9)
> pendente. import-linter 19/0, mypy strict limpo, 328 testes passam. Migration
> `0009_document_corrections`.
>
> **Revisão pós-implementação (fixes aplicados):**
> - **Satisfação na finalização:** `Proposal.submit_document_corrections` agora
>   valida que cada item em escopo é satisfeito por um documento presente do tipo,
>   distinto do sinalizado (`UnsatisfiedCorrection` → 422). Impede finalizar uma
>   emenda de documento faltante sem anexo.
> - **Escopo no use case:** `SubmitAmendmentDocument` recebe `allowed_document_types`
>   e valida o escopo (`CorrectionScopeError` → 403), simétrico ao `allowed_ids` do
>   remove; a rota apenas deriva o conjunto do token.


## Objetivo
Permitir que o staff sinalize documentos que precisam de correção **sem indeferir a
proposta**, e que o solicitante público (sem login, apenas `requesterContact`) possa
remover/substituir/incluir documentos via um canal tokenizado de escopo estreito.
`reject` continua sendo indeferimento **final**.

## Princípios / invariantes
- A proposta permanece em `PENDING` durante toda a correção.
- O token é **autorização estreita**, não acesso à proposta: só toca documentos
  explicitamente no escopo; morre no reenvio final ou quando a proposta sai de `PENDING`.
- Direção de dependência (import-linter `pyproject.toml:104`): `public_submission →
  use_of_collections` é permitido (com ignores específicos); o inverso **não**. O
  acoplamento atravessa uma **porta** definida em `use_of_collections`; a
  implementação concreta é injetada de fora dos contextos (ver §2 e §10).
- Motivos de correção vivem na **Proposal** como entidade persistente
  (`DocumentCorrectionItem`, auditável), não em note textual; o token apenas
  referencia esses itens + TTL + escopo.

---

## 1. Domínio (`use_of_collections/domain`)
**`enums.py`**
- Adicionar `ProposalEventType.DOCUMENT_CORRECTIONS_REQUESTED`.
- Adicionar `ProposalEventType.DOCUMENT_CORRECTIONS_SUBMITTED`.

**`models.py`**
- Nova entidade persistente `DocumentCorrectionItem` (dentro do agregado Proposal):
  - Campos: `id`, `document_id` (opcional — `None` para doc **faltante**),
    `document_type: DocumentType` (**obrigatório** — é o único escopo válido quando
    `document_id is None`), `reason: str`, `status` (`REQUESTED`/`RESOLVED`),
    `requested_at`, `requested_by`, `resolved_at`.
  - Motivação: auditoria + UI robustas; note textual é frágil. É a fonte de verdade do
    que foi pedido, sobrevive à morte do token, e é o que o token referencia.
  - `Proposal.correction_items: list[DocumentCorrectionItem]`.
- `Proposal.submit_documents(..., triggered_by: PermissionId | None)` — relaxar o tipo
  (hoje `PermissionId`, `models.py:591`) para permitir submissão do cidadão sem
  `PermissionId`. `Document.submitted_by` e `ProposalEvent.triggered_by` já aceitam `None`.
  - **DB já suporta:** a coluna `documents.submitted_by` **já é nullable** — a migration
    `00000006_0006_public_proposal_requester_contact.py:35` fez `DROP NOT NULL` (é o que
    faz o fluxo público atual funcionar). **Não** precisa migration nova para isso.
  - **Ajuste ORM + mapper (acoplados):** `DocumentRecord.submitted_by: Mapped[str]`
    (`infrastructure/models.py:388`) → `Mapped[str | None]`. Isso **obriga** ajustar o
    mapper `proposal_to_domain` (`repositories.py:502`): hoje faz
    `submitted_by=PermissionId(document.submitted_by)`, que em runtime já devolve `None`
    (NewType é identidade), mas com o campo virando `str | None` o **mypy `strict`
    (`pyproject.toml:56`) passa a rejeitar** (`PermissionId` espera `str`). Trocar por:
    `PermissionId(document.submitted_by) if document.submitted_by is not None else None`.
    (`is not None`, não truthiness, para não converter `""` legítimo em `None`.)
- Novo método `Proposal.request_document_corrections(occurred_at, triggered_by,
  items: list[DocumentCorrectionItem], note)`:
  - Guarda: `status == PENDING` (senão `InvalidTransition`).
  - Guarda: cada `document_id` referenciado existe em `self.documents`.
  - Anexa os `items` a `correction_items`; grava evento `DOCUMENT_CORRECTIONS_REQUESTED`.
- Novo método `Proposal.remove_document(document_id, *, allowed_ids: set)`:
  - Guarda: `status == PENDING`.
  - Guarda: `document_id in allowed_ids` (escopo do token) — nunca remove doc de staff
    nem fora do escopo.
  - Remove de `self.documents`. **Não** apaga o arquivo aqui (o caso de uso faz isso,
    espelhando `discard_uploaded_files`), para manter o domínio puro.
- Novo método `Proposal.submit_document_corrections(occurred_at, item_ids)` — chamado no
  reenvio (§6 submit), **não** deixar o endpoint só "gravar evento":
  - Guarda: `status == PENDING`.
  - Marca os `correction_items` referenciados como `RESOLVED` (`resolved_at`).
  - Grava evento `DOCUMENT_CORRECTIONS_SUBMITTED`.

## 2. Porta de saída
- Definir o Protocol na aplicação (`use_of_collections/application/ports.py`):
```python
class AmendmentInvitationPort(Protocol):
    async def invite_document_corrections(
        self, *, proposal_id, requester_email, requester_name,
        correction_item_ids: list[str],
    ) -> None: ...
```
- Escopo por **item** (consistente com §5). `document_type`/`reason` para montar o
  e-mail o adaptador obtém dos próprios `DocumentCorrectionItem`, não os duplica na
  assinatura.
- **Decisão de acoplamento (implementado):** o adaptador em `public_submission`
  **implementa a porta estruturalmente** (Protocol duck-typed — não precisa importá-la)
  e referencia `ProposalRepository`/`ProposalId` diretamente. Segue **o precedente da
  rota de intake** (`SubmitProposal`), que já importa `use_of_collections.application.
  use_cases`/`domain.models` com ignores no composition root — em vez de expandir a
  superfície de `use_of_collections.public` (que não exporta esses tipos). Um re-export
  de `AmendmentInvitationPort` em `.public` seria **código morto** (ninguém o importaria
  de lá), então **não** foi feito.
- **import-linter:** adicionar os ignores específicos das edges novas
  (`infrastructure.amendment`, `presentation.routes`, `presentation.dependencies` →
  `use_of_collections.{application.ports, application.use_cases, domain.models,
  domain.enums}`), ao lado do bloco de intake em `pyproject.toml` — mesma categoria
  "known composition-root coupling, tracked for extraction behind published facades".

## 3. Caso de uso staff (`use_of_collections/application/use_cases/proposal.py`)
- `RequestDocumentCorrections`:
  - `require_staff(caller)` — **decidido**: ação instrutória, não decisão final. É o
    análogo de `request-documents` (que já usa `require_staff`, `proposal_routes.py:539`);
    só `reject` (final) exige `require_group(CURATORIAL)`.
  - Carrega proposta; resolve `requester_email` (reusar lógica do reject,
    `proposal_routes.py:805`: `requested_by` → permission email, senão
    `requester_contact.email`).
  - `proposal.request_document_corrections(...)`.
  - `await self._invitation_port.invite_document_corrections(...)`.
  - Salva proposta.

## 4. Endpoint staff (`use_of_collections/presentation/proposal_routes.py`)
- `POST /proposals/{id}/request-document-corrections`
  - Body: **lista de itens** (cobre substituição **e** doc faltante):
    `{ items: [{ documentId?: string, documentType: string, reason: string }], note?: str }`.
    `documentId` presente ⇒ correção/substituição; ausente ⇒ doc faltante (aí
    `documentType` é o escopo). `documentType` sempre obrigatório.
  - `require_staff`, `assert_proposal_access`, `_handle_domain_errors`, `commit`.
  - Resposta: `ProposalCommandResponse` + lastEvent (padrão dos outros).

## 5. Adaptador + token (`public_submission`)
**`infrastructure/models.py`** — nova tabela `proposal_amendment_tokens`:
- `id`, `proposal_id`, `token_hash` (nunca o raw), `requester_email`,
  `correction_item_ids` (JSON/array — **escopo primário**, referencia os
  `DocumentCorrectionItem` da §1), `expires_at`, `used_at`, `created_at`.
- **Por que item_ids e não documentIds:** doc faltante não tem `document_id` para
  allowlist; o `correction_item_id` (que carrega `document_type` + `document_id?`) é o
  escopo que funciona para os dois casos. Os `document_id`/`document_type` autorizados
  derivam dos itens ainda `REQUESTED`, não são duplicados no token.

**`domain/models.py`** — `ProposalAmendmentToken` (agregado) com `is_expired(now)`,
`is_used`, `mark_used(now)`, e helpers de escopo: `may_delete(document_id)` (item
`REQUESTED` com esse `document_id`) e `may_add(document_type)` (item `REQUESTED` com
esse tipo).

**`application`** — caso de uso `IssueAmendmentToken` (gera `secrets.token_urlsafe(32)`,
guarda o hash, monta link `/{public_origin}/submit-proposal/edit?token=...`) e o
adaptador que implementa `AmendmentInvitationPort` chamando esse caso de uso + o sender.

**Persistência do `DocumentCorrectionItem` (`use_of_collections/infrastructure`)** — não
esquecer o rehydration do agregado:
- Novo `DocumentCorrectionItemRecord` + relationship `correction_items` em `ProposalRecord`
  (`infrastructure/models.py:286`, ao lado de `documents`/`requested_documents`).
- Mapear nos **dois sentidos**: `proposal_to_record` (`repositories.py:365`) e
  `proposal_to_domain` (`:433`). Sem isso o agregado não re-hidrata os itens de correção.

**`infrastructure/email.py`** — generalizar o sender: hoje `SmtpConfirmationEmailSender`
/ `LoggingConfirmationEmailSender` só fazem confirmação. Adicionar método/variante
`send_amendment_invite(to, name, link, reasons)`. **Importante:** mensagens de
`Conversation` NÃO são entregues por SMTP hoje — só o e-mail público é. Este é o único
caminho de entrega real.

## 6. Endpoints públicos tokenizados (`public_submission/presentation/routes.py`)
Reusar gates: `_read_public_upload`, `_ensure_allowed_public_file`
(PDF/JPG/PNG/DOCX), limite 10MB, rate limiter, honeypot/token. Cada handler revalida:
token existe + não usado + não expirado, e **proposta ainda em PENDING**.
- `GET /public/proposals/amendments/{token}` — hidrata a tela: dados da proposta
  (subset seguro), documentos atuais, quais estão no escopo, motivos.
- `POST /public/proposals/amendments/{token}/documents` — adiciona documento novo/substituto/faltante.
  - **Validação de escopo:** o `documentType` enviado deve casar com um item ainda
    `REQUESTED` do token (`may_add(document_type)`). Cobre doc faltante (sem `document_id`).
  - **DECISÃO: caso de uso dedicado `SubmitAmendmentDocument`** (não afrouxar
    `SubmitDocuments`). Justificativa correta:
    1. **Invariante do `caller`:** `SubmitDocuments` recebe `caller: Actor` e usa
       `data.caller.id` (`use_cases/proposal.py:330,359`). Tornar `caller: Actor | None`
       enfraqueceria, no nível de tipo, a garantia do caminho **autenticado** (permitiria
       submit sem ator) para servir um caso que não é o dele.
    2. **Escopo é regra de aplicação:** a emenda valida o upload contra o token
       (`may_add(document_type)`) — isso pertence ao use case da emenda, não a um
       `SubmitDocuments` genérico.
    - Nota: a separação de validação de tipo (.docx vs PDF/JPG/PNG/DOCX) **não** é o
      motivo — ela já vive na rota (`proposal_routes.py:589` faz o check .docx; o use case
      não valida tipo). O ganho do use case dedicado é invariante + escopo, acima.
    - `SubmitAmendmentDocument`: `submitted_by=None`, valida escopo, persiste `Document`
      e chama a mesma persistência de storage (`_file_reference`/`file_storage.save`).
- `DELETE /public/proposals/amendments/{token}/documents/{documentId}` — só se
  `may_delete(documentId)` (item `REQUESTED` com esse `document_id`); só se aplica a
  correção/substituição, não a doc faltante. Remove do agregado **e** apaga o arquivo do storage.
- `POST /public/proposals/amendments/{token}/submit` — finaliza via
  `Proposal.submit_document_corrections(...)` (§1): marca itens `RESOLVED`, grava
  `DOCUMENT_CORRECTIONS_SUBMITTED`, notifica staff, `mark_used` (single-use).

## 7. Migration (alembic)
- Tabela `proposal_amendment_tokens` (§5).
- Tabela `document_correction_items` (entidade da §1: document_id?, document_type,
  reason, status, requested_at/by, resolved_at + FK proposal_id).
- **Não** precisa alterar `documents.submitted_by` — já é nullable desde a migration
  00000006 (ver §1).
- Seguir convenção de revision ids curtos (ver commit c6d4c0c — alembic_version limitado).

## 8. Contrato + testes
- Atualizar `docs/api_contracts/11PublicProposalSubmission-API.md` com os 4 endpoints
  de amendment + o staff endpoint (e regenerar os golden contracts — ver commit b8d790d).
- Testes: `test/public_submission` (token válido/expirado/usado/fora-de-escopo,
  proposta saiu de PENDING no meio, upload inválido, DELETE fora do escopo negado) e
  `test/use_of_collections` (nova transição de domínio, guardas de `remove_document`).

## 9. Frontend (`vitarerum-ui/src/app/features/public`)
- Nova rota `submit-proposal/edit` (token via query) em `public.routes.ts`.
- Estender `PublicProposalApiService` com `loadAmendment/addDocument/removeDocument/submitAmendment`.
- Reusar a página de submissão em **modo edição**: pré-preenchida via GET, com poder
  limitado ao escopo — mostrar docs marcados + motivos, permitir remover/substituir/incluir
  faltantes e finalizar reenvio. Sem captcha por operação (rate-limit por token/IP basta).

## 10. Ligação do port acima dos contextos (composition root)
Hoje **não existe** `app.composition`; `main.py` só faz `include_router` e cada contexto
tem seu próprio `presentation/dependencies.py`. O provider FastAPI do endpoint staff mora
em `use_of_collections/presentation/dependencies.py`, que **não pode** importar
`public_submission`. Portanto:
- `use_of_collections/presentation/dependencies.py` define
  `get_amendment_invitation_port()` como provider **default** (ex.: um no-op/`Logging`
  adapter, ou `raise NotImplementedError`), e o endpoint depende dele via `Depends`.
- `main.py` (único lugar que já importa todos os contextos) faz o override real:
  `app.dependency_overrides[get_amendment_invitation_port] = <factory do adaptador em
  public_submission>`.
- Alternativa equivalente: criar um módulo `app.composition` fora dos contextos que
  monta o adaptador e é chamado por `main.py`. Escolher uma das duas — `main.py` +
  `dependency_overrides` é o menor delta.

---

## Riscos / pontos de atenção
1. **Escopo do DELETE** é o ponto de segurança nº1 — allowlist explícita no token.
2. **Entrega de e-mail é infra nova** (conversa não envia SMTP hoje).
3. **Concorrência**: staff aprova/rejeita durante emenda → endpoints públicos falham
   graciosamente (revalidar PENDING + token).
4. **Órfãos de arquivo**: remoção/substituição deve apagar o blob antigo.
5. **import-linter**: o adaptador implementa a porta estruturalmente (sem importá-la),
   mas ainda referencia `ProposalRepository`/`ProposalId` e as rotas usam os use cases +
   enums/models. Resolvido com ignores específicos no composition root, seguindo o
   precedente da rota de intake (não via `.public`, que não exporta esses tipos). Ver §2.
6. **Composition root**: o override do port vive em `main.py`/`app.composition`, nunca em
   `use_of_collections/presentation/dependencies.py` (não pode importar `public_submission`).
   Ver §10.
