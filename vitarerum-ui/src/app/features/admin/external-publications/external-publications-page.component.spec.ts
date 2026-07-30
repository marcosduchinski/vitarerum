import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Page } from '@shared/models/page.model';
import { of } from 'rxjs';
import { Mocked, vi } from 'vitest';

import { ExternalPublication, PublishableResource } from '../models/external-publication.model';
import {
  EXTERNAL_PUBLICATION_SERVICE,
  ExternalPublicationApi,
} from '../services/external-publication.service';
import { ExternalPublicationsPageComponent } from './external-publications-page.component';

const EMPTY_PAGE: Page<never> = {
  content: [],
  page: 0,
  size: 20,
  totalElements: 0,
  totalPages: 0,
};

describe('ExternalPublicationsPageComponent', () => {
  let fixture: ComponentFixture<ExternalPublicationsPageComponent>;
  let service: Mocked<ExternalPublicationApi>;

  beforeEach(async () => {
    service = {
      listPublications: vi.fn().mockReturnValue(of(EMPTY_PAGE)),
      listPublishableResources: vi.fn().mockReturnValue(of(EMPTY_PAGE)),
      createPublication: vi.fn().mockReturnValue(of(publication())),
      revokePublication: vi.fn().mockReturnValue(of(publication())),
    };

    await TestBed.configureTestingModule({
      imports: [ExternalPublicationsPageComponent],
      providers: [{ provide: EXTERNAL_PUBLICATION_SERVICE, useValue: service }],
    }).compileComponents();

    fixture = TestBed.createComponent(ExternalPublicationsPageComponent);
    fixture.detectChanges();
  });

  it('sends datetime-local expiration as an ISO instant', async () => {
    const component = fixture.componentInstance as unknown as {
      selectedResource: { set(value: PublishableResource): void };
      createExpiresAt: { set(value: string): void };
      createPublication(): Promise<void>;
    };

    component.selectedResource.set({
      id: 'project-1',
      resourceType: 'PROJECT',
      reference: 'CUP-1',
      title: 'Project',
      status: 'COMPLETED',
      subtitle: 'IN_SITU_VISIT',
    });
    component.createExpiresAt.set('2026-12-31T23:59');

    await component.createPublication();

    expect(service.createPublication).toHaveBeenCalledWith(
      expect.objectContaining({
        expiresAt: new Date('2026-12-31T23:59').toISOString(),
      }),
    );
  });
});

function publication(): ExternalPublication {
  return {
    id: 'pub-1',
    resourceType: 'PROJECT',
    resourceId: 'project-1',
    status: 'PUBLISHED',
    accessMode: 'TOKEN',
    profile: 'DETAIL',
    expiresAt: null,
    url: 'https://api.example.test/external/publications/token',
    createdAt: '2026-07-29T12:00:00Z',
    publishedAt: '2026-07-29T12:00:00Z',
    revokedAt: null,
  };
}
