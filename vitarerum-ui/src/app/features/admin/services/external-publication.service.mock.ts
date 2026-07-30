import { Injectable } from '@angular/core';
import { Page } from '@shared/models/page.model';
import { Observable, of } from 'rxjs';

import {
  CreateExternalPublicationRequest,
  ExternalPublication,
  ExternalPublicationFilters,
  PublishableResource,
  PublishableResourceFilters,
} from '../models/external-publication.model';
import { ExternalPublicationApi } from './external-publication.service';

@Injectable()
export class ExternalPublicationServiceMock implements ExternalPublicationApi {
  private readonly publications: ExternalPublication[] = [
    {
      id: 'pub-1',
      resourceType: 'PROJECT',
      resourceId: 'project-1',
      status: 'PUBLISHED',
      accessMode: 'TOKEN',
      profile: 'DETAIL',
      expiresAt: null,
      url: 'http://localhost:4200/api/v1/external/publications/mock-project-token',
      createdAt: '2026-07-29T12:00:00Z',
      publishedAt: '2026-07-29T12:00:00Z',
      revokedAt: null,
    },
  ];

  private readonly resources: PublishableResource[] = [
    {
      id: 'proposal-1',
      resourceType: 'PROPOSAL',
      reference: 'CUP-2026-0001',
      title: 'Research visit request',
      status: 'APPROVED',
      subtitle: 'IN_SITU_VISIT',
    },
    {
      id: 'project-1',
      resourceType: 'PROJECT',
      reference: 'CUP-2026-0001',
      title: 'Research visit project',
      status: 'COMPLETED',
      subtitle: 'IN_SITU_VISIT',
    },
    {
      id: 'report-1',
      resourceType: 'IN_SITU_VISIT_REPORT',
      reference: 'VISIT-2026-0001',
      title: 'Researcher visit',
      status: 'CIDOC_CONFORMANT',
      subtitle: 'Collection room',
    },
  ];

  listPublications(filters: ExternalPublicationFilters): Observable<Page<ExternalPublication>> {
    const filtered = this.publications.filter((item) => {
      const matchesType = !filters.resourceType || item.resourceType === filters.resourceType;
      const matchesStatus = !filters.status || item.status === filters.status;
      const matchesProfile = !filters.profile || item.profile === filters.profile;
      const matchesResource = !filters.resourceId || item.resourceId === filters.resourceId;
      const q = filters.q?.trim().toLowerCase();
      const matchesQuery =
        !q ||
        item.id.toLowerCase().includes(q) ||
        item.resourceId.toLowerCase().includes(q);
      return matchesType && matchesStatus && matchesProfile && matchesResource && matchesQuery;
    });
    return of(page(filtered, filters.page, filters.size));
  }

  listPublishableResources(filters: PublishableResourceFilters): Observable<Page<PublishableResource>> {
    const q = filters.q?.trim().toLowerCase();
    const filtered = this.resources.filter(
      (item) =>
        item.resourceType === filters.resourceType &&
        (!q ||
          item.id.toLowerCase().includes(q) ||
          item.reference?.toLowerCase().includes(q) ||
          item.title?.toLowerCase().includes(q)),
    );
    return of(page(filtered, filters.page, filters.size));
  }

  createPublication(request: CreateExternalPublicationRequest): Observable<ExternalPublication> {
    const created: ExternalPublication = {
      id: `pub-${this.publications.length + 1}`,
      resourceType: request.resourceType,
      resourceId: request.resourceId,
      status: 'PUBLISHED',
      accessMode: request.accessMode,
      profile: request.profile,
      expiresAt: request.expiresAt ?? null,
      url: `http://localhost:4200/api/v1/external/publications/mock-${this.publications.length + 1}`,
      createdAt: new Date().toISOString(),
      publishedAt: new Date().toISOString(),
      revokedAt: null,
    };
    this.publications.unshift(created);
    return of(created);
  }

  revokePublication(publicationId: string): Observable<ExternalPublication> {
    const idx = this.publications.findIndex((item) => item.id === publicationId);
    if (idx >= 0) {
      this.publications[idx] = {
        ...this.publications[idx],
        status: 'REVOKED',
        revokedAt: new Date().toISOString(),
        url: null,
      };
    }
    return of(this.publications[idx]);
  }
}

function page<T>(items: T[], pageNumber = 0, size = 20): Page<T> {
  const start = pageNumber * size;
  const content = items.slice(start, start + size);
  return {
    content,
    page: pageNumber,
    size,
    totalElements: items.length,
    totalPages: Math.ceil(items.length / size),
  };
}
