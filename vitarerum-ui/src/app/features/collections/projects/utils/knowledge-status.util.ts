import { ScientificReturnKnowledgeItem } from '../models/scientific-return.model';

/**
 * A retired item that was never validated is a discarded agent proposal: it
 * never reached an investigation, so calling it "retired" would blur the audit
 * trail between knowledge the institution used and knowledge it turned down.
 */
export function isDiscardedProposal(item: ScientificReturnKnowledgeItem): boolean {
  return item.status === 'RETIRED' && item.validatedAt === null;
}

export function knowledgeStatusLabel(item: ScientificReturnKnowledgeItem): string {
  if (item.status === 'PROPOSED') return 'Awaiting validation';
  if (item.status === 'RETIRED')
    return isDiscardedProposal(item) ? 'Discarded proposal' : 'Retired';
  return 'Active';
}
