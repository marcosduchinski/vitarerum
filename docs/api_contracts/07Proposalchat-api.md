# ProposalChat — AI-assisted intended-use triage

The ProposalChat is a separate bounded context (`app/ai/proposalchat`) that helps staff classify an incoming message. Given a conversation and one of its messages, it reads the email through the Use of Collections published language (`app.use_of_collections.public`, via an anti-corruption layer) and **suggests** an `intendedUse` — a `useType` drawn from the shared taxonomy plus a free-text `description`.

The suggestion is **ephemeral** (computed on demand, never stored), **advisory** (it does not mutate the proposal and records no `ProposalEvent`), and **read-only** towards the rest of the system (ProposalChat never writes back to the conversation or the proposal). Applying a suggestion is a separate action in the Use of Collections context.

All endpoints use the same authentication as the rest of the API (`Authorization` / `X-Permission-Id` headers) and the same error shape (`{ "error": "CODE", "message": "string" }`). Triage is a **staff action**: only `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, and `SYS_ADMIN` may call these endpoints; `EXTERNAL` callers (researchers) get `403`.

---

## GET /proposalchat/context

**Description** — Gathers the triage context for a focus message. Given a `conversationId` and the `messageId` of a specific message in that conversation, ProposalChat reads the conversation aggregate from the Use of Collections context through `ProposalContextReader` and returns the focus message together with a summary of the proposal it belongs to and the `intendedUse` currently recorded on that proposal. Read-only and stateless — it persists nothing and is intended for the UI to display what will be analysed before the staff member triggers a suggestion. The focus message is resolved through the conversation root, never by reaching into `Message` directly.

**Query parameters**

```
conversationId : UUID (required)
messageId      : UUID (required)
```

**Response 200 OK**

```json
{
  "conversationId": "uuid",
  "focusMessage": {
    "messageId": "uuid",
    "sentAt": "2025-01-15T10:30:00",
    "sender": "researcher@university.pt",
    "subject": "Research visit request",
    "body": "string"
  },
  "proposal": {
    "proposalId": "uuid",
    "referenceNumber": "VRP-20250115-0001",
    "title": "string",
    "status": "SUBMITTED",
    "intendedUse": {
      "useType": "IN_SITU_VISIT",
      "description": "string"
    }
  }
}
```

`focusMessage` is the message addressed by `messageId`. `proposal.intendedUse` is the value currently on the proposal (what the researcher submitted), exposed so the UI can present *current vs suggested* side by side; it may carry an empty `description`. `proposal` is always present because every conversation is tied to a proposal (`Conversation.proposalId`). ProposalChat holds no conversation state of its own — this endpoint is a translated read across the context boundary.

**Response 404 Not Found**

```json
{
  "error": "MESSAGE_NOT_FOUND",
  "message": "No message found with id uuid in conversation uuid"
}
```

The same status is returned with `"error": "CONVERSATION_NOT_FOUND"` when the conversation itself does not exist.

**Response 403 Forbidden**

```json
{
  "error": "ACCESS_DENIED",
  "message": "Triage is restricted to staff members"
}
```

---

## POST /proposalchat/intended-use-suggestions

**Description** — Runs the triage. Analyses the body of the focus message and returns a suggested `intendedUse` (a `useType` from the shared `UseType` taxonomy plus a free-text `description`), with a confidence score and a short rationale. The suggestion is **ephemeral**: computed on demand, returned once, and never stored — there is no id to fetch it back, and re-posting the same ids runs a fresh analysis. It is **advisory only**: it does not change the proposal's `intendedUse` and records no `ProposalEvent`. The response is `200 OK` rather than `201 Created` because no resource is created.

**Request body**

```json
{
  "conversationId": "uuid",
  "messageId": "uuid"
}
```

Both ids are required. They are treated as opaque references into the Use of Collections context; ProposalChat resolves them through its ACL and never persists them.

**Response 200 OK**

```json
{
  "suggestion": {
    "intendedUse": {
      "useType": "IN_SITU_VISIT",
      "description": "Researcher requests on-site consultation of 19th-century herbarium specimens in the reading room."
    },
    "confidence": 0.91,
    "rationale": "The message asks to examine physical specimens on site rather than borrow them for display.",
    "source": {
      "conversationId": "uuid",
      "messageId": "uuid"
    }
  }
}
```

`useType` is one of `EXHIBITION`, `IN_SITU_VISIT`, `OTHER` — the same taxonomy used by `Proposal` and `CollectionUseProject` (shared kernel), so an accepted suggestion drops onto the proposal without mapping. `confidence` is a float in `[0.0, 1.0]`. `rationale` is a short human-readable justification for the staff reviewer. `source` echoes the analysed ids; since nothing is persisted, this is the only provenance the caller receives.

**Response 422 Unprocessable Entity**

```json
{
  "error": "EMPTY_MESSAGE_BODY",
  "message": "The focus message has no analysable content"
}
```

Raised when the message body is blank — triage needs content. This is a domain-level rejection, distinct from the model failures below.

**Response 404 Not Found**

```json
{
  "error": "MESSAGE_NOT_FOUND",
  "message": "No message found with id uuid in conversation uuid"
}
```

**Response 403 Forbidden**

```json
{
  "error": "ACCESS_DENIED",
  "message": "Triage is restricted to staff members"
}
```

**Response 503 Service Unavailable**

```json
{
  "error": "MODEL_UNAVAILABLE",
  "message": "The language model is currently unavailable"
}
```

The output adapter (LangGraph + Ollama) could not be reached. Distinct from `422`: the input was valid, the model is down.

**Response 504 Gateway Timeout**

```json
{
  "error": "MODEL_TIMEOUT",
  "message": "The language model did not respond in time"
}
```

---

## Conventions worth noting across this group

**Staff-only.** Triage is a staff action — the attendant or curator processing an incoming email. Researchers (`EXTERNAL`) cannot call these endpoints. Authentication is the usual `Authorization` / `X-Permission-Id` session, and the caller's group is checked before any model work happens.

**Ephemeral by design.** Suggestions are never persisted: no GET by id, no list, no history. Only the `intendedUse` a human accepts — written onto the proposal in the Use of Collections context — is durable. Re-running triage on the same message always recomputes; the endpoint is safe to call repeatedly.

**Advisory, not a command.** A suggestion never changes the proposal and never emits a `ProposalEvent`. It leaves no trace in the proposal's audit trail. If traceability of AI-assisted decisions becomes a requirement, it would be introduced as an event in the Use of Collections context — not here.

**Reads through an ACL.** ProposalChat does not own `Conversation` or `Message`. It reads them from the Use of Collections context through `app.use_of_collections.public` and translates the published read model into its own domain language. It treats `conversationId` / `messageId` as opaque references, resolving the focus message via the conversation root. It never writes back across the boundary.

**Shared taxonomy.** `useType` values (`EXHIBITION`, `IN_SITU_VISIT`, `OTHER`) come from the shared `UseType`, identical to what proposals and projects use. The suggested `intendedUse` mirrors the shape of the proposal's own `intendedUse`, so the UI can diff *current vs suggested* and an accepted value applies without conversion.

**Two-step flow.** The UI typically calls `GET /proposalchat/context` first (to show the staff member which message and proposal are in scope), then `POST /proposalchat/intended-use-suggestions` when the user explicitly asks for the suggestion. The context call is optional — the POST gathers what it needs on its own — but it mirrors the "open the chat, then ask" interaction.
