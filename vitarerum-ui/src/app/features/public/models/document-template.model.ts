/**
 * A downloadable document template offered to a citizen for a given use type,
 * as exposed by the public (unauthenticated) endpoint.
 */
export interface PublicDocumentTemplate {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly mandatory: boolean;
}
