import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Page } from '@shared/models/page.model';

import { CollectionUseProjectSummary, ProjectListQuery } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectsPendingPageComponent } from './projects-pending-page.component';

const PROJECTS: readonly CollectionUseProjectSummary[] = Array.from({ length: 5 }, (_, index) => ({
  id: `project-${index + 1}`,
  referenceNumber: `VR-2026-${String(index + 41).padStart(3, '0')}`,
  title:
    index === 3
      ? 'Railway archive glass plate negatives'
      : 'Conservation study for ceramic collection',
  purpose: 'Document handling requirements before the conservation work starts.',
  type: 'IN_SITU_VISIT',
  status: 'CREATED',
  beginDate: '2026-06-10',
  endDate: '2026-06-20',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  proposal: {
    id: 'proposal-1',
    status: 'APPROVED',
    submittedAt: '2026-05-01T10:00:00',
    assignedTo: {
      permissionId: 'permission-staff',
      user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
      group: 'COLLECTIONS_MANAGEMENT',
    },
  },
}));

const PROJECT = PROJECTS[0];

class ProjectApiServiceStub {
  readonly queries: ProjectListQuery[] = [];
  readonly started: { projectId: string; note: string }[] = [];
  readonly cancelled: { projectId: string; reason: string }[] = [];

  listProjects(query: ProjectListQuery = {}) {
    this.queries.push(query);
    const page = query.page ?? 0;
    const size = query.size ?? 3;
    const start = page * size;
    const search = query.search?.toLowerCase().trim() ?? '';
    const items = search
      ? PROJECTS.filter(
          (project) =>
            project.title.toLowerCase().includes(search) ||
            project.referenceNumber.toLowerCase().includes(search),
        )
      : PROJECTS;

    return of<Page<CollectionUseProjectSummary>>({
      content: items.slice(start, start + size),
      page,
      size,
      totalElements: items.length,
      totalPages: Math.max(1, Math.ceil(items.length / size)),
    });
  }

  startProject(projectId: string, request: { note: string }) {
    this.started.push({ projectId, note: request.note });
    return of({ id: projectId, referenceNumber: PROJECT.referenceNumber, status: 'IN_PROGRESS' });
  }

  cancelProject(projectId: string, request: { reason: string }) {
    this.cancelled.push({ projectId, reason: request.reason });
    return of({ id: projectId, referenceNumber: PROJECT.referenceNumber, status: 'CANCELLED' });
  }
}

describe('ProjectsPendingPageComponent', () => {
  let identity: IdentityServiceMock;
  let projectService: ProjectApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    projectService = new ProjectApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectsPendingPageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectService },
      ],
    }).compileComponents();

    identity = TestBed.inject(IDENTITY_SERVICE) as IdentityServiceMock;
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    document.querySelectorAll('.p-menu').forEach((element) => element.remove());
  });

  it('loads accepted projects as created projects awaiting start', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 0,
      size: 3,
      search: '',
    });
  });

  it('renders pending project cards with operational information', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('VR-2026-041');
    expect(text).toContain('Conservation study for ceramic collection');
    expect(text).toContain('In-situ visit');
    expect(text).toContain('Alice Ferreira');
    expect(text).toContain('Bob Santos');
    expect(text).toContain('2026-06-10 to 2026-06-20');
    expect(text).toContain('Created - awaiting start');
    expect(text).toContain('Created projects awaiting start');
    expect(text).toContain('1-3 of 5');
    expect(compiled.querySelectorAll('.project-card')).toHaveLength(3);
  });

  it('paginates pending projects three cards at a time', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 1,
      size: 3,
      search: '',
    });
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('4-5 of 5');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('.project-card')).toHaveLength(
      2,
    );

    buttonByText(fixture.nativeElement, 'Last').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 1,
      size: 3,
      search: '',
    });
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('4-5 of 5');

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 1,
      size: 3,
      search: '',
    });

    buttonByText(fixture.nativeElement, 'First').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 0,
      size: 3,
      search: '',
    });
    expect(buttonByText(fixture.nativeElement, 'Previous').disabled).toBe(true);
  });

  it('applies and clears search from the first page', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const searchInput = compiled.querySelector<HTMLInputElement>('#pending-projects-search');

    expect(searchInput).not.toBeNull();

    searchInput!.value = 'railway';
    searchInput!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    buttonByText(compiled, 'Search').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 0,
      size: 3,
      search: 'railway',
    });
    expect(compiled.textContent).toContain('1-1 of 1');
    expect(compiled.textContent).toContain('Railway archive glass plate negatives');

    compiled.querySelector<HTMLButtonElement>('.projects-search__clear')?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'CREATED',
      page: 0,
      size: 3,
      search: '',
    });
    expect(compiled.textContent).toContain('1-3 of 5');
  });

  it('starts a pending project and reloads the list', async () => {
    await identity.signIn({ email: 'alice@ext.example.com', password: 'vita2026' });
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Start').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.started).toEqual([
      { projectId: PROJECT.id, note: 'Started from created projects awaiting start.' },
    ]);
    expect(projectService.queries).toHaveLength(2);
  });

  it('hides Start from staff users', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Start');
    expect(projectService.started).toEqual([]);
  });

  it('opens secondary actions from the popup menu', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    openActionsMenu(fixture.nativeElement, PROJECT.referenceNumber);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(document.body.textContent).toContain('Detail');
    expect(document.body.textContent).toContain('Cancel');
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Cancel');
  });

  it('navigates collections staff to the collections project detail route', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    openActionsMenu(fixture.nativeElement, PROJECT.referenceNumber);
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Detail').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/projects/collections', PROJECT.id], {
      queryParams: {
        returnTo: '/p/collections/projects/pending',
        returnLabel: 'pending projects',
      },
    });
  });

  it('navigates curatorial staff to the curatorial project detail route', async () => {
    await identity.signIn({ email: 'carol@curatorial.example.com', password: 'vita2026' });
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    openActionsMenu(fixture.nativeElement, PROJECT.referenceNumber);
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Detail').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/projects/curatorial', PROJECT.id], {
      queryParams: {
        returnTo: '/p/collections/projects/pending',
        returnLabel: 'pending projects',
      },
    });
  });

  it('navigates direction staff to the direction project detail route', async () => {
    await identity.signIn({ email: 'dan@direction.example.com', password: 'vita2026' });
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    openActionsMenu(fixture.nativeElement, PROJECT.referenceNumber);
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Detail').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/projects/direction', PROJECT.id], {
      queryParams: {
        returnTo: '/p/collections/projects/pending',
        returnLabel: 'pending projects',
      },
    });
  });

  it('confirms cancelling a pending project from the popup menu and reloads the list', async () => {
    const fixture = TestBed.createComponent(ProjectsPendingPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    openActionsMenu(fixture.nativeElement, PROJECT.referenceNumber);
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Cancel').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.cancelled).toEqual([]);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Cancel project?');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'This will cancel VR-2026-041 before work starts and move it to cancelled projects.',
    );

    buttonByText(fixture.nativeElement, 'Cancel project').click();
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(projectService.cancelled).toEqual([
      { projectId: PROJECT.id, reason: 'Cancelled from created projects awaiting start.' },
    ]);
    expect(projectService.queries).toHaveLength(2);
  });
});

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === text,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${text}`);
  }

  return button;
}

function openActionsMenu(root: HTMLElement, referenceNumber: string): void {
  const button = root.querySelector<HTMLButtonElement>(
    `[aria-label="More actions for ${referenceNumber}"]`,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Actions menu button not found: ${referenceNumber}`);
  }

  button.click();
}

function menuItemByText(text: string): HTMLElement {
  const item = Array.from(
    document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
  ).find((candidate) => candidate.textContent?.trim() === text);

  if (!(item instanceof HTMLElement)) {
    throw new Error(`Menu item not found: ${text}`);
  }

  return item;
}
