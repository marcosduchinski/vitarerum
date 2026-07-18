# AI prompts admin API

Base path: `/api/v1/ai/prompts`

All endpoints are staff-only in V1. Authorization is currently mapped to the
same staff policy used by narrative generation.

## List templates

`GET /api/v1/ai/prompts`

Optional query params:

- `purpose`: one of `in_situ_narrative`, `museum_question_triage`,
  `proposal_assistance`, `project_assistance`
- `status`: one of `draft`, `published`, `archived`

Response `200 OK`:

```json
[
  {
    "id": "prompt-template-uuid",
    "purpose": "in_situ_narrative",
    "key": "system_institutional",
    "name": "Institutional narrative",
    "description": "Prompt for institutional narratives.",
    "variablesSchemaJson": "{\"type\":\"object\"}",
    "activeVersionId": "prompt-version-uuid",
    "createdAt": "2026-07-18T10:00:00Z"
  }
]
```

## List versions

`GET /api/v1/ai/prompts/{templateId}/versions`

Response `200 OK`:

```json
[
  {
    "id": "prompt-version-uuid",
    "templateId": "prompt-template-uuid",
    "version": 1,
    "versionLabel": "museum-narrative-institutional-v1",
    "status": "published",
    "content": "System prompt text...",
    "defaultTemperature": 0.3,
    "createdBy": "system",
    "createdAt": "2026-07-18T10:00:00Z",
    "publishedBy": "system",
    "publishedAt": "2026-07-18T10:00:00Z",
    "archivedAt": null
  }
]
```

## Get version

`GET /api/v1/ai/prompts/versions/{versionId}`

Returns the immutable content of that exact version. This is the endpoint used
by audit-oriented views when they need to inspect the prompt used by a past
narrative.

## Create draft

`POST /api/v1/ai/prompts/{templateId}/versions`

Request:

```json
{
  "version_label": "museum-narrative-institutional-v2",
  "content": "Revised system prompt text...",
  "default_temperature": 0.3,
  "source_version_id": null
}
```

Response `201 Created`: a version response with `status = "draft"`.

## Publish draft

`POST /api/v1/ai/prompts/versions/{versionId}/publish`

Publishes a draft atomically: archives the currently published version for the
same template, publishes the draft, and updates `activeVersionId`.

Response `200 OK`: a version response with `status = "published"`.

## Archive version

`POST /api/v1/ai/prompts/versions/{versionId}/archive`

Archives only non-published versions. A published version can only be archived
as part of publishing its replacement.

Response `200 OK`: a version response with `status = "archived"`.

## Errors

- `403 INSUFFICIENT_GROUP`: caller is not staff.
- `404 PROMPT_TEMPLATE_NOT_FOUND`: template id does not exist.
- `404 PROMPT_VERSION_NOT_FOUND`: version id does not exist.
- `409 PROMPT_PUBLICATION_CONFLICT`: publish conflicts with state or a
  concurrent publication.
- `409 PUBLISHED_PROMPT_REQUIRED`: isolated archive would remove the published
  prompt.
