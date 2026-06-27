import { ComponentRef, computed, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';

import {
  CreateInSituVisitReportRequest,
  InSituVisitReport,
} from '../../../reports/models/report.model';
import { REPORTS_API_SERVICE } from '../../../reports/services/reports-api.service';
import { CollectionUseProjectDetail, ProjectEventsPage } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectCuratorialDetailPageComponent } from './project-curatorial-detail-page.component';

const PROJECT: CollectionUseProjectDetail = {
  id: 'proj-22',
  referenceNumber: 'VR-2026-022',
  title: 'Curatorial specimen access',
  purpose: 'Review object handling during a supervised research visit.',
  type: 'IN_SITU_VISIT',
  status: 'CREATED',
  result: null,
  beginDate: '2026-07-01',
  endDate: '2026-08-15',
  requestedBy: {
    permissionId: 'perm-alice',
    user: { id: 'u-alice', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  proposal: {
    id: 'prop-22',
    status: 'APPROVED',
    assignedTo: {
      permissionId: 'perm-carol',
      user: { id: 'u-carol', name: 'Carol Souza', email: 'carol@example.test' },
      group: 'CURATORIAL',
    },
  },
  actions: {
    canStart: false,
    canComplete: false,
    canCancel: true,
    canOpenLog: true,
    canCreateObjectLogEntry: true,
    canCreateOccurrenceEntry: true,
  },
  staffContext: null,
};

const EVENTS_PAGE: ProjectEventsPage = {
  projectId: PROJECT.id,
  content: [
    {
      occurredAt: '2026-06-01T09:00:00Z',
      type: 'REQUESTED',
      triggeredBy: PROJECT.requestedBy!,
      note: null,
    },
  ],
  page: 0,
  size: 20,
  totalElements: 1,
  totalPages: 1,
};

class ProjectApiServiceStub {
  project: CollectionUseProjectDetail = PROJECT;
  readonly cancelled: { projectId: string; reason: string }[] = [];

  getProject() {
    return of(this.project);
  }

  listEvents() {
    return of(EVENTS_PAGE);
  }

  cancelProject(projectId: string, request: { reason: string }) {
    this.cancelled.push({ projectId, reason: request.reason });
    return of({
      id: projectId,
      referenceNumber: this.project.referenceNumber,
      status: 'CANCELLED' as const,
      result: 'CANCELLED' as const,
      lastEvent: EVENTS_PAGE.content[0],
    });
  }
}

class IdentityServiceStub implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>({
    accessToken: 'token',
    user: { id: 'u-carol', email: 'carol@example.test', displayName: 'Carol Souza' },
    group: 'CURATORIAL',
    availableGroups: ['CURATORIAL', 'COLLECTIONS_MANAGEMENT', 'DIRECTION'],
    permissions: [
      { permissionId: 'perm-carol', group: 'CURATORIAL' },
      { permissionId: 'perm-carol-collections', group: 'COLLECTIONS_MANAGEMENT' },
      { permissionId: 'perm-carol-direction', group: 'DIRECTION' },
    ],
  });

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isStaff = computed(() => {
    const group = this.session()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  signIn(credentials: LoginRequest): Promise<void> {
    void credentials;
    return Promise.resolve();
  }

  signOut(): void {
    this.sessionState.set(null);
  }

  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    const session = this.session();
    return (
      session?.permissions?.find((permission) => permission.group === session.group)
        ?.permissionId ?? null
    );
  }

  setGroup(group: GroupName): void {
    const session = this.session();
    if (session) this.sessionState.set({ ...session, group });
  }

  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = this.session();
    if (session) this.sessionState.set({ ...session, availableGroups: groups });
  }
}

class ReportsApiServiceStub {
  readonly created: { projectId: string; request: CreateInSituVisitReportRequest }[] = [];

  createInSituVisitReport(projectId: string, request: CreateInSituVisitReportRequest) {
    this.created.push({ projectId, request });
    return of<InSituVisitReport>({
      id: 'report-1',
      createdAt: '2026-06-22T10:30:00Z',
      createdBy: 'perm-carol',
      projectId,
      narrativeId: 'narrative-1',
      inSituVisitRecordId: 'record-1',
    });
  }
}

describe('ProjectCuratorialDetailPageComponent', () => {
  let projectService: ProjectApiServiceStub;
  let identity: IdentityServiceStub;
  let reportsService: ReportsApiServiceStub;
  let router: Router;
  let componentRef: ComponentRef<ProjectCuratorialDetailPageComponent>;

  beforeEach(async () => {
    projectService = new ProjectApiServiceStub();
    identity = new IdentityServiceStub();
    reportsService = new ReportsApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectCuratorialDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectService },
        { provide: IDENTITY_SERVICE, useValue: identity },
        { provide: REPORTS_API_SERVICE, useValue: reportsService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(ProjectCuratorialDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', PROJECT.id);
    componentRef.setInput('returnTo', '/p/collections/projects/my');
    componentRef.setInput('returnLabel', 'my projects');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders overview by default with accessible tabs', async () => {
    const compiled = await render();

    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'Overview',
    );
    expect(compiled.textContent).toContain('Curatorial specimen access');
    expect(compiled.textContent).toContain('Review object handling');
    expect(compiled.textContent).toContain('Alice Ferreira');
    expect(compiled.textContent).toContain('Carol Souza');
    expect(compiled.querySelector('#overview-panel')).not.toBeNull();
  });

  it('switches to the tasks tab and shows the cancel task', async () => {
    const compiled = await render();

    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'Actions',
    );
    expect(compiled.querySelector('#tasks-panel')).not.toBeNull();
    expect(compiled.textContent).toContain('Cancel project');
    expect(buttonByText(compiled, 'Cancel project').disabled).toBe(false);
  });

  it('switches to the frontend-only TODO List tab', async () => {
    const compiled = await render();

    tabByName(compiled, 'TODO List').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'TODO List',
    );
    expect(compiled.querySelector('#todo-panel')).not.toBeNull();
    expect(compiled.textContent).toContain('Items are kept only for this demonstration');
    expect(projectService.cancelled).toEqual([]);
  });

  it('disables the cancel task when project actions do not allow it', async () => {
    projectService.project = {
      ...PROJECT,
      status: 'COMPLETED',
      actions: { ...PROJECT.actions, canCancel: false },
    };

    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(compiled.textContent).toContain('This task is unavailable for the current status.');
    expect(buttonByText(compiled, 'Cancel project').disabled).toBe(true);
  });

  it('keeps the cancel task available for cancellable projects when actions are absent', async () => {
    const projectWithoutActions: Record<string, unknown> = { ...PROJECT };
    delete projectWithoutActions['actions'];
    projectService.project = projectWithoutActions as unknown as CollectionUseProjectDetail;

    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(buttonByText(compiled, 'Cancel project').disabled).toBe(false);
  });

  it('shows object access and occurrence log tasks for in-progress projects', async () => {
    projectService.project = {
      ...PROJECT,
      type: 'EXHIBITION',
      status: 'IN_PROGRESS',
    };

    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();

    const accessLogLink = linkByText(compiled, 'Open access log');
    const occurrenceLogLink = linkByText(compiled, 'Open occurrence log');

    expect(compiled.textContent).toContain('Object access log');
    expect(compiled.textContent).toContain('Object occurrence log');
    expect(accessLogLink.getAttribute('href')).toBe(
      '/p/collections/projects/proj-22/log/exhibition',
    );
    expect(occurrenceLogLink.getAttribute('href')).toBe(
      '/p/collections/projects/proj-22/occurrences/exhibition',
    );
  });

  it('shows in-situ visit report creation for curatorial and collections groups', async () => {
    projectService.project = { ...PROJECT, status: 'COMPLETED' };
    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(compiled.textContent).toContain('Reports');
    expect(compiled.textContent).toContain('In-situ visit narrative report');
    expect(compiled.textContent).toContain('Create new In Situ Visit Report');

    identity.setGroup('COLLECTIONS_MANAGEMENT');
    componentRef.changeDetectorRef.detectChanges();
    expect(compiled.textContent).toContain('Create new In Situ Visit Report');
  });

  it('hides report creation for direction and non-in-situ projects', async () => {
    identity.setGroup('DIRECTION');
    projectService.project = { ...PROJECT, status: 'COMPLETED' };
    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();
    expect(compiled.textContent).not.toContain('Create new In Situ Visit Report');

    identity.setGroup('CURATORIAL');
    projectService.project = { ...PROJECT, type: 'EXHIBITION', status: 'COMPLETED' };
    const exhibitionCompiled = await render();
    tabByName(exhibitionCompiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();
    expect(exhibitionCompiled.textContent).not.toContain('Create new In Situ Visit Report');
  });

  it('hides report creation until the in-situ project is completed', async () => {
    identity.setGroup('CURATORIAL');

    for (const status of ['CREATED', 'IN_PROGRESS', 'CANCELLED'] as const) {
      projectService.project = { ...PROJECT, status };
      const compiled = await render();
      tabByName(compiled, 'Actions').click();
      componentRef.changeDetectorRef.detectChanges();
      expect(compiled.textContent).not.toContain('Create new In Situ Visit Report');
    }
  });

  it('creates a report with the selected options and shows success feedback', async () => {
    projectService.project = { ...PROJECT, status: 'COMPLETED' };
    const compiled = await render();
    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();
    buttonByText(compiled, 'Create new In Situ Visit Report').click();
    componentRef.changeDetectorRef.detectChanges();

    changeSelect(selectById(compiled, 'report-target-language'), 'en');
    changeSelect(selectById(compiled, 'report-narrative-type'), 'scientific');
    changeInput(inputById(compiled, 'report-creativity'), '0.6');
    componentRef.changeDetectorRef.detectChanges();
    buttonByText(compiled, 'Create report').click();
    await new Promise<void>((resolve) => setTimeout(resolve));
    componentRef.changeDetectorRef.detectChanges();

    expect(reportsService.created).toEqual([
      {
        projectId: PROJECT.id,
        request: {
          targetLanguage: 'en',
          narrativeType: 'scientific',
          creativityTemperature: 0.6,
        },
      },
    ]);
    expect(compiled.textContent).toContain('In-situ visit report created');
    expect(compiled.textContent).toContain('report-1');
  });

  it('confirms cancellation and navigates to cancelled projects', async () => {
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const compiled = await render();

    tabByName(compiled, 'Actions').click();
    componentRef.changeDetectorRef.detectChanges();
    buttonByText(compiled, 'Cancel project').click();
    componentRef.changeDetectorRef.detectChanges();

    expect(compiled.textContent).toContain('Cancel project?');

    buttonByText(compiled, 'Cancel project').click();
    await componentRef.changeDetectorRef.detectChanges();
    await new Promise<void>((resolve) => setTimeout(resolve));

    expect(projectService.cancelled).toEqual([
      { projectId: PROJECT.id, reason: 'Cancelled from curatorial project detail.' },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/projects/cancelled']);
  });
});

function tabByName(
  root: HTMLElement,
  name: 'Overview' | 'Actions' | 'TODO List',
): HTMLButtonElement {
  const tab = Array.from(root.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((item) =>
    item.textContent?.includes(name),
  );
  expect(tab).not.toBeNull();
  return tab!;
}

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent?.includes(text),
  );
  expect(button).not.toBeNull();
  return button!;
}

function linkByText(root: HTMLElement, text: string): HTMLAnchorElement {
  const link = Array.from(root.querySelectorAll<HTMLAnchorElement>('a')).find((item) =>
    item.textContent?.includes(text),
  );
  expect(link).not.toBeNull();
  return link!;
}

function selectById(root: HTMLElement, id: string): HTMLSelectElement {
  const select = root.querySelector<HTMLSelectElement>(`#${id}`);
  expect(select).not.toBeNull();
  return select!;
}

function inputById(root: HTMLElement, id: string): HTMLInputElement {
  const input = root.querySelector<HTMLInputElement>(`#${id}`);
  expect(input).not.toBeNull();
  return input!;
}

function changeSelect(element: HTMLSelectElement, value: string): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

function changeInput(element: HTMLInputElement, value: string): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}
