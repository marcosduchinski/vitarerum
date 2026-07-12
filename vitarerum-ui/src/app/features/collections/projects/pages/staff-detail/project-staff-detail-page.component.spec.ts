import { signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';

import { CollectionUseProjectDetail, ProjectEventsPage } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { REPORTS_API_SERVICE } from '../../../reports/services/reports-api.service';
import { ProjectStaffDetailPageComponent } from './project-staff-detail-page.component';

let currentProject: CollectionUseProjectDetail;

const PROJECT: CollectionUseProjectDetail = {
  id: 'proj-12',
  referenceNumber: 'CUP-DAF9DC7D',
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
  content: [],
  page: 0,
  size: 20,
  totalElements: 0,
  totalPages: 1,
};

class IdentityServiceStub {
  readonly session = signal({ group: 'COLLECTIONS_MANAGEMENT' }).asReadonly();
  readonly isAuthenticated = signal(true).asReadonly();
}

class ProjectApiServiceStub {
  readonly started: { id: string; note: string }[] = [];
  readonly completed: { id: string; note: string }[] = [];

  getProject() {
    return of(currentProject);
  }

  listEvents() {
    return of(EVENTS_PAGE);
  }

  startProject(id: string, request: { note: string }) {
    this.started.push({ id, note: request.note });
    return of({ id, referenceNumber: PROJECT.referenceNumber, status: 'IN_PROGRESS' });
  }

  completeProject(id: string, request: { note: string }) {
    this.completed.push({ id, note: request.note });
    return of({ id, referenceNumber: PROJECT.referenceNumber, status: 'COMPLETED' });
  }

  cancelProject() {
    return of({ id: PROJECT.id, referenceNumber: PROJECT.referenceNumber, status: 'CANCELLED' });
  }
}

class ReportsApiServiceStub {
  createInSituVisitReport() {
    return of({});
  }
}

describe('ProjectStaffDetailPageComponent', () => {
  let projectService: ProjectApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    currentProject = { ...PROJECT };
    projectService = new ProjectApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectStaffDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
        { provide: PROJECT_API_SERVICE, useValue: projectService },
        { provide: REPORTS_API_SERVICE, useClass: ReportsApiServiceStub },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  it('starts created staff projects from the Actions section', async () => {
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Start project').click();
    fixture.detectChanges();
    await fixture.whenStable();
    buttonByText(fixture.nativeElement, 'Start project').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.started).toEqual([
      { id: PROJECT.id, note: 'Started from staff project detail.' },
    ]);
  });

  it('completes in-progress staff projects from the Actions section', async () => {
    currentProject = {
      ...PROJECT,
      status: 'IN_PROGRESS',
      actions: { ...PROJECT.actions, canStart: false, canComplete: true },
    };
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Complete project').click();
    fixture.detectChanges();
    await fixture.whenStable();
    buttonByText(fixture.nativeElement, 'Complete project').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(projectService.completed).toEqual([
      { id: PROJECT.id, note: 'Completed from staff project detail.' },
    ]);
  });

  it('navigates completed staff projects to the blank follow-up screen', async () => {
    currentProject = {
      ...PROJECT,
      status: 'COMPLETED',
      result: 'COMPLETED',
      actions: { ...PROJECT.actions, canStart: false, canComplete: false, canCancel: false },
    };
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Create follow-up project').click();

    expect(navigate).toHaveBeenCalledWith([
      '/p/collections/projects',
      PROJECT.id,
      'follow-up',
      'new',
    ]);
  });
});

function buttonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).not.toBeNull();
  return button!;
}
