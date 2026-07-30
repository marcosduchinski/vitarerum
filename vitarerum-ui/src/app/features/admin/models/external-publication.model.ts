import { PageQuery } from '@shared/models/page.model';

export type ExternalPublicationResourceType = 'PROPOSAL' | 'PROJECT' | 'IN_SITU_VISIT_REPORT';
export type ExternalPublicationStatus = 'PUBLISHED' | 'REVOKED';
export type ExternalPublicationAccessMode = 'TOKEN' | 'INTEGRATION_CLIENT';
export type ExternalPublicationProfile = 'SUMMARY' | 'DETAIL' | 'JSON_LD';

export interface ExternalPublication {
  readonly id: string;
  readonly resourceType: ExternalPublicationResourceType;
  readonly resourceId: string;
  readonly status: ExternalPublicationStatus;
  readonly accessMode: ExternalPublicationAccessMode;
  readonly profile: ExternalPublicationProfile;
  readonly expiresAt: string | null;
  readonly url: string | null;
  readonly createdAt: string;
  readonly publishedAt: string;
  readonly revokedAt: string | null;
}

export interface CreateExternalPublicationRequest {
  readonly resourceType: ExternalPublicationResourceType;
  readonly resourceId: string;
  readonly accessMode: ExternalPublicationAccessMode;
  readonly profile: ExternalPublicationProfile;
  readonly expiresAt?: string | null;
}

export interface ExternalPublicationFilters extends PageQuery {
  readonly resourceType?: ExternalPublicationResourceType | null;
  readonly resourceId?: string | null;
  readonly status?: ExternalPublicationStatus | null;
  readonly profile?: ExternalPublicationProfile | null;
  readonly q?: string | null;
}

export interface PublishableResource {
  readonly id: string;
  readonly resourceType: ExternalPublicationResourceType;
  readonly reference: string | null;
  readonly title: string | null;
  readonly status: string | null;
  readonly subtitle: string | null;
}

export interface PublishableResourceFilters extends PageQuery {
  readonly resourceType: ExternalPublicationResourceType;
  readonly q?: string | null;
}
