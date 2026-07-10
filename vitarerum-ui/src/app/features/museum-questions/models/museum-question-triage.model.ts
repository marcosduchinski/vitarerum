/** AI triage of a museum question: in/out-of-scope suggestion, drafted
 * out-of-scope reply, and — when in scope and an object is named — the
 * catalogue search results for it. Mirrors the backend's `TriageResponse`. */

export type TriageVerdict = 'IN_SCOPE' | 'OUT_OF_SCOPE';

export type MentionedObjectOrigin = 'AI' | 'STAFF';

/** An object/specimen name extracted from the question, kept in both
 * languages so the catalogue can be searched in either. `origin` says
 * whether the AI extracted it or staff added/edited it afterwards. */
export interface MentionedObject {
  readonly english: string;
  readonly portuguese: string;
  readonly origin: MentionedObjectOrigin;
}

/** What the frontend *sends* to `PUT .../triage/search-terms` — deliberately
 * without `origin`: the backend computes provenance from the diff against
 * what's persisted, never accepts it as client input. */
export interface SearchTermDraft {
  readonly english: string;
  readonly portuguese: string;
}

/** Deliberately its own type, not features/objects' `ObjectSearchHit`: the
 * triage backend persists/returns only these 4 fields (a display-only
 * snapshot), not the full search hit shape (sourceDocumentId, sheet,
 * rowNumber, cells). Reusing `ObjectSearchHit` here would claim fields the
 * API never sends. */
export interface ObjectTriageHit {
  readonly collectionId: string;
  readonly collectionName: string;
  readonly fileName: string;
  readonly highlight: string;
}

/** Search results for one mentioned object — searched in both languages,
 * hits merged and deduplicated on the backend. `languagesSearched` records
 * which of "pt"/"en" were actually queried (English is skipped when
 * identical to Portuguese). */
export interface ObjectTriageMatch {
  readonly english: string;
  readonly portuguese: string;
  readonly hits: readonly ObjectTriageHit[];
  readonly languagesSearched: readonly string[];
}

export interface MuseumQuestionTriage {
  readonly id: string;
  readonly questionId: string;
  readonly verdict: TriageVerdict;
  /** The verdict that actually applies: `staffOverrideVerdict` if staff
   * contested it, otherwise the AI's own `verdict`. Display logic should
   * always read this, never `verdict` directly. */
  readonly effectiveVerdict: TriageVerdict;
  readonly staffOverrideVerdict: TriageVerdict | null;
  readonly isVisitRelated: boolean;
  readonly mentionedObjects: readonly MentionedObject[];
  readonly objectMatches: readonly ObjectTriageMatch[];
  readonly suggestedReply: string | null;
  /** Human-readable description of the catalogue search strategy used —
   * present only while `effectiveVerdict` is `IN_SCOPE`. */
  readonly searchStrategy: string | null;
  readonly modelName: string;
  readonly createdAt: string;
}
