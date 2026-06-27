import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Page } from '@shared/models/page.model';

import { CollectionUseProjectSummary, ProjectListQuery } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectsCompletedPageComponent } from './projects-completed-page.component';

const PROJECTS: readonly CollectionUseProjectSummary[] = Array.from({ length: 25 }, (_, index) => ({
  id: `project-${index + 1}`,
  referenceNumber: `VR-2026-${String(index + 81).padStart(3, '0')}`,
  title: index === 4 ? 'Completed railway archive conservation' : 'Completed manuscript access',
  purpose: 'Completed collection-use work with staff supervision.',
  type: index % 3 === 1 ? 'EXHIBITION' : index % 3 === 2 ? 'OTHER' : 'IN_SITU_VISIT',
  status: 'COMPLETED',
  result: 'COMPLETED',
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

const DETAIL_ROUTE_CASES = [
  {
    label: 'collections management',
    email: 'bob@collections.example.com',
    route: ['/p/collections/projects/collections', 'project-1'],
  },
  {
    label: 'curatorial',
    email: 'carol@curatorial.example.com',
    route: ['/p/collections/projects/curatorial', 'project-1'],
  },
  {
    label: 'direction',
    email: 'dan@direction.example.com',
    route: ['/p/collections/projects/direction', 'project-1'],
  },
  {
    label: 'external fallback',
    email: 'alice@ext.example.com',
    route: ['/p/collections/projects', 'project-1'],
  },
] as const;

class ProjectApiServiceStub {
  readonly queries: ProjectListQuery[] = [];

  listProjects(query: ProjectListQuery = {}) {
    this.queries.push(query);
    const page = query.page ?? 0;
    const size = query.size ?? 20;
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
}

describe('ProjectsCompletedPageComponent', () => {
  let projectService: ProjectApiServiceStub;
  let identity: IdentityServiceMock;
  let router: Router;

  beforeEach(async () => {
    projectService = new ProjectApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectsCompletedPageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    identity = TestBed.inject(IDENTITY_SERVICE) as IdentityServiceMock;
  });

  afterEach(() => {
    identity.signOut();
    document.querySelectorAll('.p-menu').forEach((element) => element.remove());
  });

  it('loads completed projects only', async () => {
    const fixture = TestBed.createComponent(ProjectsCompletedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 20,
      search: '',
    });
  });

  it('renders the completed table with project information', async () => {
    const fixture = TestBed.createComponent(ProjectsCompletedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('Reference');
    expect(text).toContain('Assigned staff');
    expect(text).toContain('VR-2026-081');
    expect(text).toContain('Completed manuscript access');
    expect(text).toContain('In-situ visit');
    expect(text).toContain('Alice Ferreira');
    expect(text).toContain('Bob Santos');
    expect(text).toContain('1-20 of 25 projects');
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-081"]')).not.toBeNull();
  });

  it.each(DETAIL_ROUTE_CASES)(
    'links and navigates $label users to the correct project detail',
    async ({ email, route }) => {
      await identity.signIn({ email, password: 'vita2026' });
      const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
      const fixture = TestBed.createComponent(ProjectsCompletedPageComponent);
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();

      const titleLink = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
        '.projects-table__title',
      );
      expect(titleLink?.getAttribute('href')).toContain(route.join('/'));
      expect(titleLink?.getAttribute('href')).toContain(
        'returnTo=%2Fp%2Fcollections%2Fprojects%2Fcompleted',
      );

      (fixture.nativeElement as HTMLElement)
        .querySelector<HTMLButtonElement>('[aria-label="More actions for VR-2026-081"]')!
        .click();
      fixture.detectChanges();
      await fixture.whenStable();

      const details = Array.from(
        document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
      ).find((item) => item.textContent?.trim() === 'Details');
      details!.click();

      expect(navigateSpy).toHaveBeenCalledWith([...route], {
        queryParams: {
          returnTo: '/p/collections/projects/completed',
          returnLabel: 'completed projects',
        },
      });
    },
  );

  it('applies and clears search from the first page', async () => {
    const fixture = TestBed.createComponent(ProjectsCompletedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const searchInput = compiled.querySelector<HTMLInputElement>('#completed-projects-search');

    expect(searchInput).not.toBeNull();

    searchInput!.value = 'railway';
    searchInput!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    buttonByText(compiled, 'Search').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 20,
      search: 'railway',
    });
    expect(compiled.textContent).toContain('1-1 of 1 projects');
    expect(compiled.textContent).toContain('Completed railway archive conservation');

    compiled.querySelector<HTMLButtonElement>('.projects-search__clear')?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 20,
      search: '',
    });
  });

  it('changes page size and keeps pagination within bounds', async () => {
    const fixture = TestBed.createComponent(ProjectsCompletedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 1,
      size: 20,
      search: '',
    });

    const pageSize = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#completed-projects-page-size',
    );

    expect(pageSize).not.toBeNull();

    pageSize!.value = '10';
    pageSize!.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 0,
      size: 10,
      search: '',
    });

    buttonByText(fixture.nativeElement, 'Last').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 2,
      size: 10,
      search: '',
    });

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.queries.at(-1)).toEqual({
      status: 'COMPLETED',
      page: 2,
      size: 10,
      search: '',
    });
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
