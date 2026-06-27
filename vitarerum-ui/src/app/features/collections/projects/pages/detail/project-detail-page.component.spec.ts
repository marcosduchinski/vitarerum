import { ComponentRef, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { CollectionUseProjectDetail, ProjectEventsPage } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectDetailPageComponent } from './project-detail-page.component';

let currentProject: CollectionUseProjectDetail;
let currentSession: ReturnType<typeof signal<{ group: string } | null>>;

class IdentityServiceStub {
  readonly session = currentSession.asReadonly();
  readonly isAuthenticated = signal(true).asReadonly();
}

const PROJECT: CollectionUseProjectDetail = {
  id: 'proj-12',
  referenceNumber: 'VR-2026-012',
  title: 'Atlantic forest zoology specimens',
  purpose: 'Comparative study of specimen records.',
  type: 'IN_SITU_VISIT',
  status: 'CREATED',
  beginDate: '2026-07-01',
  endDate: '2026-12-31',
  requestedBy: {
    permissionId: 'perm-alice',
    user: { id: 'u-alice', name: 'Alice Ferreira', email: 'alice@ext.example.com' },
    group: 'EXTERNAL',
  },
  proposal: {
    id: 'prop-12',
    status: 'APPROVED',
    assignedTo: {
      permissionId: 'perm-bob',
      user: { id: 'u-bob', name: 'Bob Santos', email: 'bob@collections.example.com' },
      group: 'COLLECTIONS_MANAGEMENT',
    },
  },
  actions: {
    canStart: true,
    canComplete: false,
    canCancel: true,
    canOpenLog: false,
    canCreateObjectLogEntry: false,
    canCreateOccurrenceEntry: false,
  },
  staffContext: null,
};

const EVENTS_PAGE: ProjectEventsPage = {
  projectId: 'proj-12',
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
  getProject() {
    return of(currentProject);
  }
  listEvents() {
    return of(EVENTS_PAGE);
  }
  startProject(id: string) {
    return of({
      id,
      referenceNumber: 'VR-2026-012',
      status: 'IN_PROGRESS' as const,
      result: null,
      lastEvent: EVENTS_PAGE.content[0],
    });
  }
  completeProject(id: string) {
    return of({
      id,
      referenceNumber: 'VR-2026-012',
      status: 'COMPLETED' as const,
      result: 'COMPLETED' as const,
      lastEvent: EVENTS_PAGE.content[0],
    });
  }
  cancelProject(id: string) {
    return of({
      id,
      referenceNumber: 'VR-2026-012',
      status: 'CANCELLED' as const,
      result: 'CANCELLED' as const,
      lastEvent: EVENTS_PAGE.content[0],
    });
  }
}

describe('ProjectDetailPageComponent', () => {
  let componentRef: ComponentRef<ProjectDetailPageComponent>;

  beforeEach(async () => {
    currentProject = { ...PROJECT };
    currentSession = signal<{ group: string } | null>({ group: 'COLLECTIONS_MANAGEMENT' });

    await TestBed.configureTestingModule({
      imports: [ProjectDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useClass: ProjectApiServiceStub },
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
      ],
    }).compileComponents();
  });

  it('renders project overview with reference, title, status and events', async () => {
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('VR-2026-012');
    expect(text).toContain('Atlantic forest zoology specimens');
    expect(text).toContain('Alice Ferreira');
    expect(text).toContain('Bob Santos');
    expect(text).toContain('REQUESTED');
  });

  it('renders nullable researcher-only requester details without failing', async () => {
    currentProject = { ...PROJECT, requestedBy: null };
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('Requested by');
    expect(text).toContain('-');
  });

  it('shows Start project button for external researchers when CREATED', async () => {
    currentSession.set({ group: 'EXTERNAL' });
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    selectTab(fixture.nativeElement, 'Actions');
    fixture.detectChanges();

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).map((b) => b.textContent?.trim());
    expect(buttons.some((t) => t?.includes('Start project'))).toBe(true);
  });

  it('hides Start project button from staff users when CREATED', async () => {
    currentSession.set({ group: 'COLLECTIONS_MANAGEMENT' });
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    selectTab(fixture.nativeElement, 'Actions');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Start project');
  });

  it('uses safe return inputs for the back link', () => {
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    componentRef.setInput('returnTo', '/p/collections/projects/pending');
    componentRef.setInput('returnLabel', 'pending projects');
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('a[href="/p/collections/projects/pending"]')).not.toBeNull();
    expect(el.textContent).toContain('Back to pending projects');
  });

  it('disables log and completion tasks for terminal projects', async () => {
    currentProject = { ...PROJECT, status: 'CANCELLED', result: 'CANCELLED' };
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    selectTab(fixture.nativeElement, 'Actions');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    const accessLogLink = linkByText(fixture.nativeElement, 'Open access log');
    const occurrenceLogLink = linkByText(fixture.nativeElement, 'Open occurrence log');
    const completeButton = buttonByText(fixture.nativeElement, 'Complete project');
    const cancelButton = buttonByText(fixture.nativeElement, 'Cancel project');

    expect(text).toContain('This task is available once the project is in progress.');
    expect(accessLogLink.hasAttribute('href')).toBe(false);
    expect(occurrenceLogLink.hasAttribute('href')).toBe(false);
    expect(completeButton.disabled).toBe(true);
    expect(cancelButton.disabled).toBe(true);
  });

  it('blocks external researchers from opening the log before the project is in progress', async () => {
    currentSession.set({ group: 'EXTERNAL' });
    currentProject = { ...PROJECT, status: 'CREATED' };
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    selectTab(fixture.nativeElement, 'Actions');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    const accessLogLink = linkByText(fixture.nativeElement, 'Open access log');
    const occurrenceLogLink = linkByText(fixture.nativeElement, 'Open occurrence log');

    expect(text).toContain('This task is available once the project is in progress.');
    expect(accessLogLink.hasAttribute('href')).toBe(false);
    expect(occurrenceLogLink.hasAttribute('href')).toBe(false);
  });

  it('lets external researchers open access and occurrence logs while the project is in progress', async () => {
    currentSession.set({ group: 'EXTERNAL' });
    currentProject = { ...PROJECT, status: 'IN_PROGRESS' };
    const fixture = TestBed.createComponent(ProjectDetailPageComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    selectTab(fixture.nativeElement, 'Actions');
    fixture.detectChanges();

    const accessLogLink = linkByText(fixture.nativeElement, 'Open access log');
    const occurrenceLogLink = linkByText(fixture.nativeElement, 'Open occurrence log');
    const completeButton = buttonByText(fixture.nativeElement, 'Complete project');

    expect(accessLogLink.getAttribute('href')).toBe('/p/collections/projects/proj-12/log/research');
    expect(occurrenceLogLink.getAttribute('href')).toBe(
      '/p/collections/projects/proj-12/occurrences/research',
    );
    expect(completeButton.disabled).toBe(false);
  });
});

function selectTab(root: HTMLElement, label: 'Overview' | 'Actions'): void {
  const tab = Array.from(root.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((button) =>
    button.textContent?.includes(label),
  );
  expect(tab).not.toBeNull();
  tab!.click();
}

function buttonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).not.toBeNull();
  return button!;
}

function linkByText(root: HTMLElement, label: string): HTMLAnchorElement {
  const link = Array.from(root.querySelectorAll<HTMLAnchorElement>('a')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(link).not.toBeNull();
  return link!;
}
