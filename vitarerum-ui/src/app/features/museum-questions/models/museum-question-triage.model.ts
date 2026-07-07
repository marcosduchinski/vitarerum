/** AI triage of a museum question: in/out-of-scope suggestion, drafted
 * out-of-scope reply, and — when in scope and an object is named — the
 * catalogue search results for it. Mirrors the backend's `TriageResponse`. */

export type TriageVerdict = 'IN_SCOPE' | 'OUT_OF_SCOPE';

/** An object/specimen name extracted from the question, kept in both
 * languages so the catalogue can be searched in either. */
export interface MentionedObject {
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
 * hits merged and deduplicated on the backend. */
export interface ObjectTriageMatch {
  readonly english: string;
  readonly portuguese: string;
  readonly hits: readonly ObjectTriageHit[];
}

export interface MuseumQuestionTriage {
  readonly id: string;
  readonly questionId: string;
  readonly verdict: TriageVerdict;
  readonly isVisitRelated: boolean;
  readonly mentionedObjects: readonly MentionedObject[];
  readonly objectMatches: readonly ObjectTriageMatch[];
  readonly suggestedReply: string | null;
  readonly modelName: string;
  readonly createdAt: string;
}
