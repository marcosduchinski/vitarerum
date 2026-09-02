import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { Observable, of, Subject } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';

import { CollectionUseProjectSummary } from '../../models/project.model';
import {
  CreateScientificReturnWatchRequest,
  ScientificReturnWatch,
  ScientificReturnWatchLookupResponse,
  ScientificReturnWatchStatus,
} from '../../models/scientific-return.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';
import { ProjectWatchersPageComponent } from './project-watchers-page.component';

const PROJECTS: readonly CollectionUseProjectSummary[] = [
  {
    id: 'project-1',
    referenceNumber: 'PRJ-001',
    title: 'Reptile research',
    purpose: 'Research',
    type: 'OTHER',
    status: 'COMPLETED',
    result: 'COMPLETED',
    beginDate: '2026-01-01',
    endDate: '2026-02-01',
    requestedBy: null,
  },
  {
    id: 'project-2',
    referenceNumber: 'PRJ-002',
    title: 'Empty project',
    purpose: 'Research',
    type: 'OTHER',
    status: 'COMPLETED',
    result: 'COMPLETED',
    beginDate: '2026-01-01',
    endDate: '2026-02-01',
    requestedBy: null,
  },
];

function watch(status: ScientificReturnWatchStatus = 'PAUSED'): ScientificReturnWatch {
  return {
    id: 'watch-1',
    projectId: 'project-1',
    status,
    reviewIntervalDays: 90,
    createdBy: 'permission-1',
    createdAt: '2026-08-26T00:00:00Z',
    lastRunAt: null,
    nextRunAt: '2026-08-26T00:00:00Z',
    scheduleAnchorAt: '2026-08-26T00:00:00Z',
    projectSnapshotId: 'snapshot-1',
  };
}

class ProjectApiStub {
  readonly queries: object[] = [];

  listProjects(query: object): Observable<{
    content: readonly CollectionUseProjectSummary[];
    page: number;
    size: number;
    totalElements: number;
    totalPages: number;
  }> {
    this.queries.push(query);
    return of({ content: PROJECTS, page: 0, size: 20, totalElements: 2, totalPages: 1 });
  }
}

class WatchApiStub {
  readonly lookups: string[][] = [];
  readonly creates: { projectId: string; request: CreateScientificReturnWatchRequest }[] = [];
  createResponse: Subject<ScientificReturnWatch> | null = null;

  lookupWatches(projectIds: readonly string[]): Observable<ScientificReturnWatchLookupResponse> {
    this.lookups.push([...projectIds]);
    return of({
      items: [
        { projectId: 'project-1', watch: null, eligible: true, ineligibilityReason: null },
        {
          projectId: 'project-2',
          watch: null,
          eligible: false,
          ineligibilityReason: 'NO_CONSULTED_OBJECTS',
        },
      ],
    });
  }

  createWatch(
    projectId: string,
    request: CreateScientificReturnWatchRequest,
  ): Observable<ScientificReturnWatch> {
    this.creates.push({ projectId, request });
    return this.createResponse ?? of(watch());
  }

  updateWatch(): Observable<ScientificReturnWatch> {
    return of(watch());
  }

  changeWatchStatus(
    _watchId: string,
    status: ScientificReturnWatchStatus,
  ): Observable<ScientificReturnWatch> {
    return of(watch(status));
  }
}

describe('ProjectWatchersPageComponent', () => {
  let fixture: ComponentFixture<ProjectWatchersPageComponent>;
  let projectsApi: ProjectApiStub;
  let watchersApi: WatchApiStub;

  beforeEach(async () => {
    const session = signal<IdentitySession | null>({
      accessToken: 'token',
      user: { id: 'user-1', email: 'curator@example.test', displayName: 'Curator' },
      group: 'CURATORIAL',
      availableGroups: ['CURATORIAL'],
      permissions: [{ permissionId: 'permission-1', group: 'CURATORIAL' }],
    });
    projectsApi = new ProjectApiStub();
    watchersApi = new WatchApiStub();
    await TestBed.configureTestingModule({
      imports: [ProjectWatchersPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectsApi },
        { provide: ScientificReturnApiService, useValue: watchersApi },
        {
          provide: IDENTITY_SERVICE,
          useValue: {
            session: session.asReadonly(),
            isAuthenticated: computed(() => true),
            isStaff: computed(() => true),
            getPermissionId: () => 'permission-1',
          },
        },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ProjectWatchersPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('loads completed projects and their watches in two batched requests', () => {
    expect(projectsApi.queries).toEqual([{ status: 'COMPLETED', page: 0, size: 20, search: '' }]);
    expect(watchersApi.lookups).toEqual([['project-1', 'project-2']]);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('PRJ-001');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Not eligible');
  });

  it('uses the shared project-list table and pagination structure', () => {
    const host = fixture.nativeElement as HTMLElement;

    expect(host.querySelectorAll('.watchers-table colgroup col')).toHaveLength(7);
    expect(host.querySelector('.watchers-table__ref')?.textContent).toContain('PRJ-001');
    expect(host.querySelector('.watchers-table__title')?.textContent).toContain('Reptile research');
    expect(host.querySelector('.watchers-pagination__meta')).not.toBeNull();
    expect(host.querySelector('.watchers-pagination__controls')).not.toBeNull();
    expect(host.querySelector('.watchers-pagination__page')?.getAttribute('aria-live')).toBe(
      'polite',
    );
  });

  it('hides bulk selection and configuration replication controls', () => {
    const host = fixture.nativeElement as HTMLElement;

    expect(host.querySelector('.bulk-bar')).toBeNull();
    expect(host.querySelector('input[type="checkbox"]')).toBeNull();
    expect(host.textContent).not.toContain('Use as source');
    expect(host.textContent).not.toContain('Replicate configuration');
    expect(host.textContent).not.toContain('Apply selected');
    expect(host.querySelector('input[type="date"]')).not.toBeNull();
    expect(host.querySelector('input[type="number"]')).not.toBeNull();
  });

  it('clears the search and reloads the unfiltered project list', async () => {
    const host = fixture.nativeElement as HTMLElement;
    const search = host.querySelector<HTMLInputElement>('#watchers-search');
    expect(search).not.toBeNull();

    search!.value = 'reptile';
    search!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const searchButton = [...host.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Search',
    );
    expect(searchButton).toBeDefined();
    searchButton!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(projectsApi.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 20,
      search: 'reptile',
    });

    const clearButton = host.querySelector<HTMLButtonElement>(
      'button[aria-label="Clear watcher project search"]',
    );
    expect(clearButton).not.toBeNull();
    clearButton!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(host.querySelector<HTMLInputElement>('#watchers-search')?.value).toBe('');
    expect(projectsApi.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 20,
      search: '',
    });
  });

  it('creates an eligible watcher paused and disables an ineligible project', async () => {
    const buttons = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')];
    const createButtons = buttons.filter((button) => button.textContent?.trim() === 'Create');

    expect(createButtons).toHaveLength(2);
    expect(createButtons[1].disabled).toBe(true);
    createButtons[0].click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(watchersApi.creates).toHaveLength(1);
    expect(watchersApi.creates[0].request.startImmediately).toBe(false);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Watcher created and paused.',
    );
  });

  it('does not select an ineligible row through the component handler', () => {
    const component = fixture.componentInstance as unknown as {
      toggleSelected(projectId: string, checked: boolean): void;
      selectedCount(): number;
    };

    component.toggleSelected('project-2', true);

    expect(component.selectedCount()).toBe(0);
  });

  it('prevents a second bulk apply while the first one is running', async () => {
    const pendingCreate = new Subject<ScientificReturnWatch>();
    watchersApi.createResponse = pendingCreate;
    const component = fixture.componentInstance as unknown as {
      toggleSelected(projectId: string, checked: boolean): void;
      applySelected(): Promise<void>;
      selectedCount(): number;
    };
    component.toggleSelected('project-1', true);

    const firstApply = component.applySelected();
    const secondApply = component.applySelected();

    expect(watchersApi.creates).toHaveLength(1);
    pendingCreate.next(watch());
    pendingCreate.complete();
    await Promise.all([firstApply, secondApply]);
    expect(component.selectedCount()).toBe(0);
  });
});
