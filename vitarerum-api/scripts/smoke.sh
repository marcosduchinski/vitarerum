#!/usr/bin/env bash
#
# End-to-end smoke test of the use-of-collections workflow against a running API,
# including the ProposalChat AI triage (staff-only).
#
# Prerequisites:
#   1. API running (locally or via docker compose), e.g.:
#        uv run uvicorn app.main:app --reload
#        # or:  docker compose up -d --build
#   2. Identities seeded once:
#        docker compose exec -T postgres psql -U vitarerum -d vitarerum < scripts/seed.sql
#   3. `curl` and `jq` installed.
#   4. For the suggestion call: a reachable Ollama with the configured model
#        (`ollama pull llama3.1:8b`). When absent the step is skipped, not fatal.
#
# Usage:
#   ./scripts/smoke.sh                 # happy path: submit -> approve -> run -> complete
#   WORKFLOW=reject ./scripts/smoke.sh # submit -> assign -> reject
#   WORKFLOW=cancel ./scripts/smoke.sh # submit -> approve -> cancel project before start
#
# Overridable env: BASE, EXT_PERM, CUR_PERM, WORKFLOW.

set -euo pipefail

BASE="${BASE:-http://localhost:8000/api/v1}"
EXT_PERM="${EXT_PERM:-perm-ext}"   # EXTERNAL requester
CUR_PERM="${CUR_PERM:-perm-cur}"   # CURATORIAL curator
EXT_EMAIL="${EXT_EMAIL:-researcher@uni.pt}"
CUR_EMAIL="${CUR_EMAIL:-curator@museum.pt}"
PASSWORD="${PASSWORD:-password}"   # seeded password for both users
WORKFLOW="${WORKFLOW:-happy}"

command -v jq >/dev/null   || { echo "jq is required"; exit 1; }
command -v curl >/dev/null || { echo "curl is required"; exit 1; }

JSON=(-H "Content-Type: application/json")

# Authenticate and echo the access token (fails loudly on non-2xx).
login() { # email
  local resp code
  resp="$(curl -sS -w '\n%{http_code}' "${JSON[@]}" -X POST "$BASE/auth/login" \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}")"
  code="${resp##*$'\n'}"
  if [[ "$code" != 2* ]]; then echo "LOGIN FAILED ($code): ${resp%$'\n'*}" >&2; exit 1; fi
  jq -r .accessToken <<<"${resp%$'\n'*}"
}

EXT_TOKEN="$(login "$EXT_EMAIL")"
CUR_TOKEN="$(login "$CUR_EMAIL")"

EXT=(-H "X-Permission-Id: ${EXT_PERM}" -H "Authorization: Bearer ${EXT_TOKEN}")
CUR=(-H "X-Permission-Id: ${CUR_PERM}" -H "Authorization: Bearer ${CUR_TOKEN}")

# Dummy upload files (the API only checks the .docx extension / declared mediaType).
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf 'dummy form\n'  > "$TMP/form.docx"
printf 'dummy image\n' > "$TMP/photo.jpg"

step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

# POST JSON and fail loudly on non-2xx, printing the body.
post_json() { # url body header-array-expansion...
  local url="$1" body="$2"; shift 2
  local resp code
  resp="$(curl -sS -w '\n%{http_code}' "${JSON[@]}" "$@" -X POST "$url" -d "$body")"
  code="${resp##*$'\n'}"; body="${resp%$'\n'*}"
  if [[ "$code" != 2* ]]; then echo "FAILED ($code): $body" >&2; exit 1; fi
  echo "$body"
}

step "Submit proposal (EXTERNAL) — seeds the conversation's first message"
submit="$(post_json "$BASE/proposals" '{
  "title":"Manuscript study",
  "intendedUse":{"useType":"OTHER","description":""},
  "purpose":"Study the codex",
  "beginDate":"2026-07-01","endDate":"2026-07-15",
  "initialMessageSubject":"Research visit request",
  "initialMessageBody":"Dear collections team, I would like to come on site to examine the medieval codex in the reading room for my palaeography research. I do not need to borrow it.",
  "requestedObjects":[{"inventoryNumber":"INV-001","category":"manuscript","description":"Medieval codex"}]
}' "${EXT[@]}")"
PID="$(jq -r .proposal.id <<<"$submit")"
CONV="$(jq -r .conversationId <<<"$submit")"
echo "proposal=$PID  conversation=$CONV"
echo "proposal.status = $(jq -r .proposal.status <<<"$submit")  (current intendedUse: $(jq -r .proposal.intendedUse.useType <<<"$submit"))"

step "ProposalChat AI triage (staff): read context, then suggest intendedUse"
MID="$(curl -sS "${CUR[@]}" "$BASE/proposals/$PID/conversation" | jq -r '.messages[0].id')"
curl -sS "${CUR[@]}" \
  "$BASE/proposalchat/context?conversationId=$CONV&messageId=$MID" \
  | jq '{conversationId, focus: .focusMessage.subject, current: .proposal.intendedUse.useType}'
# The suggestion needs a reachable Ollama; tolerate 503/504 so the smoke run
# does not abort when the model is not running.
sug="$(curl -sS -w '\n%{http_code}' "${JSON[@]}" "${CUR[@]}" \
  -X POST "$BASE/proposalchat/intended-use-suggestions" \
  -d "{\"conversationId\":\"$CONV\",\"messageId\":\"$MID\"}")"
scode="${sug##*$'\n'}"; sbody="${sug%$'\n'*}"
if [[ "$scode" == 2* ]]; then
  jq '.suggestion | {suggested: .intendedUse.useType, confidence, rationale}' <<<"$sbody"
else
  echo "suggestion skipped (HTTP $scode): $(jq -r '.error // .' <<<"$sbody" 2>/dev/null || echo "$sbody")"
fi

step "Curator assigns the proposal to themselves (SUBMITTED -> PENDING)"
post_json "$BASE/proposals/$PID/assign" \
  "{\"targetPermissionId\":\"$CUR_PERM\",\"note\":\"I will handle this\"}" "${CUR[@]}" \
  | jq '{status, lastEvent: .lastEvent.type}'

step "Request documents (stays PENDING; records DOCUMENTS_REQUESTED)"
post_json "$BASE/proposals/$PID/request-documents" '{
  "requiredDocuments":[{"type":"RESEARCH_FORM","description":"Signed form"}],
  "note":"Please send the research form"}' "${CUR[@]}" \
  | jq '{status, lastEvent: .lastEvent.type}'

step "Conversation reply (EXTERNAL) + .docx upload"
post_json "$BASE/proposals/$PID/conversation/messages" '{
  "recipient":"collections@museum.pt","subject":"RE: form","body":"Attached."}' "${EXT[@]}" \
  | jq '{id, subject}'
curl -sS "${EXT[@]}" -X POST "$BASE/proposals/$PID/documents" \
  -F "documentType=RESEARCH_FORM" -F "file=@$TMP/form.docx" | jq '{id, type, fileName}'

if [[ "$WORKFLOW" == "reject" ]]; then
  step "Reject (PENDING -> REJECTED)"
  post_json "$BASE/proposals/$PID/reject" '{"reason":"out of scope"}' "${CUR[@]}" \
    | jq '{status, lastEvent: .lastEvent.type}'
  echo; echo "Workflow 'reject' complete."
  exit 0
fi

step "Approve (PENDING -> APPROVED; creates the collection-use project)"
approve="$(post_json "$BASE/proposals/$PID/approve" '{
  "title":"Manuscript study","purpose":"Study the codex",
  "beginDate":"2026-07-01","endDate":"2026-07-15","note":"granted"}' "${CUR[@]}")"
PROJ="$(jq -r .collectionUseProject.id <<<"$approve")"
echo "project=$PROJ"
jq '{proposal: .proposal.status, project: .collectionUseProject.status}' <<<"$approve"

if [[ "$WORKFLOW" == "cancel" ]]; then
  step "Cancel project before start (CREATED -> CANCELLED)"
  post_json "$BASE/collection-use-projects/$PROJ/cancel" '{"reason":"withdrawn"}' "${EXT[@]}" \
    | jq '{status, result, lastEvent: .lastEvent.type}'
  echo; echo "Workflow 'cancel' complete."
  exit 0
fi

step "Start project (CREATED -> IN_PROGRESS)"
post_json "$BASE/collection-use-projects/$PROJ/start" '{"note":"begun"}' "${EXT[@]}" \
  | jq '{status, lastEvent: .lastEvent.type}'

step "Add object-access log entry (update) + image attachment"
entry="$(post_json "$BASE/collection-use-projects/$PROJ/log-entries" '{
  "inventoryNumber":"INV-001","numberOfObjects":1,
  "observations":"Inspected folios 1-20"}' "${EXT[@]}")"
EID="$(jq -r .id <<<"$entry")"
jq '{id, inventory: .objectReference.inventoryNumber, observations}' <<<"$entry"
curl -sS "${EXT[@]}" \
  -X POST "$BASE/collection-use-projects/$PROJ/log-entries/$EID/attachments" \
  -F "mediaType=IMAGE" -F "file=@$TMP/photo.jpg" | jq '{fileName, mediaType}'

step "Add object-occurrence entry (incident)"
post_json "$BASE/collection-use-projects/$PROJ/occurrence-entries" '{
  "inventoryNumber":"INV-001","numberOfObjects":1,
  "occurrenceDate":"2026-07-02T10:00:00","location":"Reading room",
  "detailedDescription":"Minor tear noted on folio 12"}' "${EXT[@]}" \
  | jq '{id, location, detailedDescription}'

step "Add publication entry (researcher, while IN_PROGRESS)"
post_json "$BASE/collection-use-projects/$PROJ/publication-entries" '{
  "note":"Preprint shared with the museum"}' "${EXT[@]}" | jq '{id, note}'

step "Complete project (IN_PROGRESS -> COMPLETED)"
post_json "$BASE/collection-use-projects/$PROJ/complete" '{"note":"done"}' "${EXT[@]}" \
  | jq '{status, result, lastEvent: .lastEvent.type}'

step "Post-completion: curator adds a publication entry (researcher cannot once COMPLETED)"
post_json "$BASE/collection-use-projects/$PROJ/publication-entries" '{
  "note":"Final publication catalogued"}' "${CUR[@]}" | jq '{id, note}'

step "Worklist views"
echo "-- proposal events --"
curl -sS "${CUR[@]}" "$BASE/proposals/$PID/events" | jq '[.content[].type]'
echo "-- project events --"
curl -sS "${CUR[@]}" "$BASE/collection-use-projects/$PROJ/events" | jq '[.content[].type]'
echo "-- requester: my projects --"
curl -sS "${EXT[@]}" "$BASE/collection-use-projects" | jq '[.content[] | {id, status}]'

echo; echo "Workflow 'happy' complete."
