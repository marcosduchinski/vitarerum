import { computed, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';

import {
  ScientificReturnKnowledgeItem,
  ScientificReturnKnowledgePage,
  ScientificReturnKnowledgeQuery,
} from '../../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../../services/scientific-return-api.service';
import { ScientificReturnKnowledgeBasePageComponent } from './scientific-return-knowledge-base-page.component';

const ITEM: ScientificReturnKnowledgeItem = {
  id: 'knowledge-1',
  institutionId: 'institution-1',
  kind: 'INVENTORY_VARIATION_EXAMPLE',
  status: 'ACTIVE',
  content: 'The publication omitted internal zeroes.',
  registeredNumber: 'MUHNAC/MB06-005747',
  observedForm: 'MB06-5747',
  supersedesId: null,
  sourceCandidateId: null,
  sourceDecisionId: null,
  proposedByModel: null,
  promptVersion: null,
  createdBy: 'permission-1',
  createdByDetail: {
    permissionId: 'permission-1',
    name: 'Curator One',
    email: 'curator@example.test',
    group: 'CURATORIAL',
  },
  createdAt: '2026-08-30T10:00:00Z',
  validatedBy: 'permission-1',
  validatedByDetail: null,
  validatedAt: '2026-08-30T10:00:00Z',
  retiredBy: null,
  retiredByDetail: null,
  retiredAt: null,
};

class IdentityStub {
  readonly state = signal<IdentitySession | null>({
    accessToken: 'token',
    user: { id: 'user-1', email: 'curator@example.test', displayName: 'Curator One' },
    group: 'CURATORIAL',
    availableGroups: ['CURATORIAL'],
    permissions: [{ permissionId: 'permission-1', group: 'CURATORIAL' }],
  });
  readonly session = this.state.asReadonly();
  readonly isAuthenticated = computed(() => true);
  readonly isStaff = computed(() => true);
  getPermissionId(): string {
    return 'permission-1';
  }
}

class ApiStub {
  queries: ScientificReturnKnowledgeQuery[] = [];
  page: ScientificReturnKnowledgePage = {
    content: [ITEM],
    page: 0,
    size: 25,
    totalElements: 1,
    totalPages: 1,
    counts: { active: 1, proposed: 0, retired: 0 },
  };

  listKnowledgeItems(
    query: ScientificReturnKnowledgeQuery,
  ): Observable<ScientificReturnKnowledgePage> {
    this.queries.push(query);
    return of(this.page);
  }

  getKnowledgeHistory(): Observable<readonly ScientificReturnKnowledgeItem[]> {
    return of([ITEM]);
  }
}

describe('ScientificReturnKnowledgeBasePageComponent', () => {
  let fixture: ComponentFixture<ScientificReturnKnowledgeBasePageComponent>;
  let api: ApiStub;

  beforeEach(async () => {
    api = new ApiStub();
    await TestBed.configureTestingModule({
      imports: [ScientificReturnKnowledgeBasePageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityStub },
        { provide: ScientificReturnApiService, useValue: api },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ScientificReturnKnowledgeBasePageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('shows institutional counts, audit metadata, and management actions', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Knowledge Base');
    expect(text).toContain('Available to investigations');
    expect(text).toContain('MUHNAC/MB06-005747');
    expect(text).toContain('Curator One');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector(
        '[aria-label="More actions for this knowledge item"]',
      ),
    ).not.toBeNull();
  });

  it('uses the summary counts as toggleable status filters', async () => {
    const activeSummary = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[data-status="ACTIVE"]',
    )!;

    activeSummary.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)).toMatchObject({ status: 'ACTIVE', page: 0 });
    expect(activeSummary.getAttribute('aria-pressed')).toBe('true');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Filtering by');

    activeSummary.click();
    await fixture.whenStable();

    expect(api.queries.at(-1)).toMatchObject({ status: null, page: 0 });
  });

  it('opens the inventory editor in the wide structured layout', () => {
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('app-page-header button.primary')!.click();
    fixture.detectChanges();

    expect(root.querySelector('.confirm-modal__dialog--wide')).not.toBeNull();
    expect(root.querySelector('.inventory-fields')).not.toBeNull();
    expect(root.textContent).toContain('Canonical number in the collection');
    expect(root.textContent).toContain('Form printed in the publication');
  });

  it('sends exact inventory and status filters to the API', async () => {
    const root = fixture.nativeElement as HTMLElement;
    const inventory = root.querySelector<HTMLInputElement>('input[type="search"]')!;
    const selects = root.querySelectorAll<HTMLSelectElement>('select');
    inventory.value = 'MB06-5747';
    selects[0].value = 'ACTIVE';
    root
      .querySelector<HTMLFormElement>('.knowledge-filters')!
      .dispatchEvent(new SubmitEvent('submit', { bubbles: true }));
    await fixture.whenStable();

    expect(api.queries.at(-1)).toMatchObject({
      status: 'ACTIVE',
      inventoryNumber: 'MB06-5747',
      page: 0,
    });
  });
});
