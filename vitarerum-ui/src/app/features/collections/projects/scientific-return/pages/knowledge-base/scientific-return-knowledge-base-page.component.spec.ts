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

const PROPOSAL: ScientificReturnKnowledgeItem = {
  ...ITEM,
  id: 'knowledge-2',
  status: 'PROPOSED',
  content: 'Publications sometimes drop the institutional prefix.',
  sourceCandidateId: 'candidate-1',
  sourceDecisionId: 'decision-1',
  proposedByModel: 'gemini-2.5-flash',
  promptVersion: 'scientific-return-full-agentic-learning-v1',
  validatedBy: null,
  validatedAt: null,
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
    content: [ITEM, PROPOSAL],
    page: 0,
    size: 25,
    totalElements: 2,
    totalPages: 1,
    counts: { active: 1, proposed: 1, retired: 0 },
  };
  retired: string[] = [];
  activated: string[] = [];

  listKnowledgeItems(
    query: ScientificReturnKnowledgeQuery,
  ): Observable<ScientificReturnKnowledgePage> {
    this.queries.push(query);
    return of(this.page);
  }

  getKnowledgeHistory(): Observable<readonly ScientificReturnKnowledgeItem[]> {
    return of([ITEM]);
  }

  activateKnowledgeItem(itemId: string): Observable<ScientificReturnKnowledgeItem> {
    this.activated.push(itemId);
    return of(ITEM);
  }

  retireKnowledgeItem(itemId: string): Observable<ScientificReturnKnowledgeItem> {
    this.retired.push(itemId);
    const discarded: ScientificReturnKnowledgeItem = {
      ...PROPOSAL,
      status: 'RETIRED',
      retiredBy: 'permission-1',
      retiredAt: '2026-08-31T12:00:00Z',
    };
    this.page = { ...this.page, content: [ITEM, discarded] };
    return of(discarded);
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

  it('shows the catalogue, audit metadata, and management actions', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Knowledge Base');
    expect(text).toContain('MUHNAC/MB06-005747');
    expect(text).toContain('Curator One');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector(
        '[aria-label="More actions for this knowledge item"]',
      ),
    ).not.toBeNull();
  });

  it('opens the inventory editor in the wide structured layout', () => {
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('.filter-actions button.primary')!.click();
    fixture.detectChanges();

    expect(root.querySelector('.confirm-modal__dialog--wide')).not.toBeNull();
    expect(root.querySelector('.inventory-fields')).not.toBeNull();
    expect(root.textContent).toContain('Canonical number in the collection');
    expect(root.textContent).toContain('Form printed in the publication');
  });

  it('discards an agent proposal without ever activating it', async () => {
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('button.discard')!.click();
    fixture.detectChanges();
    expect(root.textContent).toContain('Discard this proposal?');

    root.querySelector<HTMLButtonElement>('.confirm-modal__button--primary')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.retired).toEqual(['knowledge-2']);
    expect(api.activated).toEqual([]);
    expect(root.textContent).toContain('The proposal was discarded.');
    expect(root.textContent).toContain('Discarded proposal');
    expect(root.textContent).not.toContain('Discard proposal');
  });

  it('sends the free-text search and status filters to the API', async () => {
    const root = fixture.nativeElement as HTMLElement;
    const term = root.querySelector<HTMLInputElement>('input[type="search"]')!;
    const selects = root.querySelectorAll<HTMLSelectElement>('select');
    term.value = 'MB06-5747';
    selects[0].value = 'ACTIVE';
    root
      .querySelector<HTMLFormElement>('.knowledge-filters')!
      .dispatchEvent(new SubmitEvent('submit', { bubbles: true }));
    await fixture.whenStable();

    expect(api.queries.at(-1)).toMatchObject({
      status: 'ACTIVE',
      q: 'MB06-5747',
      page: 0,
    });
  });

  it('searches words of a lesson that carries no inventory citation', async () => {
    const root = fixture.nativeElement as HTMLElement;
    const term = root.querySelector<HTMLInputElement>('input[type="search"]')!;
    term.value = 'institutional prefix';
    root
      .querySelector<HTMLFormElement>('.knowledge-filters')!
      .dispatchEvent(new SubmitEvent('submit', { bubbles: true }));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)).toMatchObject({ q: 'institutional prefix', page: 0 });
    expect(root.textContent).toContain('Search: institutional prefix');
  });
});
