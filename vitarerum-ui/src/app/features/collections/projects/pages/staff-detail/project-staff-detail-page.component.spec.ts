import { signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { OBJECT_SEARCH_SERVICE } from '@features/objects/services/object-search.service';

import {
  CollectionUseProjectDetail,
  ProjectEventsPage,
  ProjectObjectDependencySummary,
  RemoveProjectObjectRequest,
} from '../../models/project.model';
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
  readonly addedObjects: { id: string; request: unknown }[] = [];
  readonly removedObjects: { id: string; objectId: string }[] = [];
  readonly cascadeRemovedObjects: {
    id: string;
    objectId: string;
    request: RemoveProjectObjectRequest;
  }[] = [];
  removeConflict: ProjectObjectDependencySummary | null = null;

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

  addProjectObjects(id: string, request: unknown) {
    this.addedObjects.push({ id, request });
    return of(currentProject);
  }

  removeProjectObject(id: string, objectId: string) {
    this.removedObjects.push({ id, objectId });
    if (this.removeConflict) {
      return throwError(
        () =>
          new HttpErrorResponse({
            status: 409,
            error: {
              error: 'PROJECT_OBJECT_HAS_DEPENDENCIES',
              message: 'This project object has related records.',
              dependencies: this.removeConflict,
            },
          }),
      );
    }
    return of(void 0);
  }

  removeProjectObjectCascade(id: string, objectId: string, request: RemoveProjectObjectRequest) {
    this.cascadeRemovedObjects.push({ id, objectId, request });
    return of(void 0);
  }
}

class ReportsApiServiceStub {
  createInSituVisitReport() {
    return of({});
  }
}

class ObjectSearchServiceStub {
  search() {
    return of({ items: [], page: 0, size: 20, totalElements: 0, totalPages: 0 });
  }

  listSearchableCollections() {
    return of([]);
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
        { provide: OBJECT_SEARCH_SERVICE, useClass: ObjectSearchServiceStub },
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

  it('shows the Edit link in the Actions tab for editable projects', async () => {
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(
      fixture.nativeElement.querySelector('.project-detail__header a.project-detail__edit'),
    ).toBeNull();
    const link = fixture.nativeElement.querySelector('a.project-detail__edit');
    expect(link).not.toBeNull();
    expect(link!.getAttribute('href')).toBe('/p/collections/projects/collections/proj-12/edit');
  });

  it('hides the Edit link for a completed project', async () => {
    currentProject = {
      ...PROJECT,
      status: 'COMPLETED',
      result: 'COMPLETED',
      actions: { ...PROJECT.actions, canStart: false, canComplete: false, canCancel: false },
    };
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('a.project-detail__edit')).toBeNull();
  });

  it('groups actions, objects, and todo list below the overview in tabs', async () => {
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const el: HTMLElement = fixture.nativeElement;
    const tabs = Array.from(el.querySelectorAll<HTMLElement>('[role="tab"]'));
    expect(tabs.map((tab) => tab.textContent?.trim().replace(/\s+/g, ' '))).toEqual([
      'Actions',
      'Objects',
      'Todo List',
    ]);
    expect(el.querySelector<HTMLElement>('#actions-tab')?.getAttribute('aria-selected')).toBe(
      'true',
    );
  });

  it('adds and removes project objects through the Objects section', async () => {
    currentProject = {
      ...PROJECT,
      objects: [
        {
          id: 'project-object-1',
          inventoryNumber: 'INV-001',
          displayTitle: 'Book of Hours',
          objectName: 'Illuminated manuscript',
          briefDescriptionSnapshot: null,
          category: 'manuscript',
          description: '',
        },
      ],
    };
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const el: HTMLElement = fixture.nativeElement;
    buttonByText(el, 'Objects').click();
    fixture.detectChanges();

    el.querySelector<HTMLButtonElement>('.object-row__remove')!.click();
    fixture.detectChanges();
    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.trim() === 'Remove object')!
      .click();
    await fixture.whenStable();

    expect(projectService.removedObjects).toEqual([
      { id: PROJECT.id, objectId: 'project-object-1' },
    ]);
  });

  it('requires a reason before removing project objects with related records', async () => {
    currentProject = {
      ...PROJECT,
      objects: [
        {
          id: 'project-object-1',
          inventoryNumber: 'INV-001',
          displayTitle: 'Book of Hours',
          objectName: 'Illuminated manuscript',
          briefDescriptionSnapshot: null,
          category: 'manuscript',
          description: '',
        },
      ],
    };
    projectService.removeConflict = {
      accessLogEntries: 1,
      occurrenceEntries: 2,
      publicationEntries: 1,
      attachments: 3,
    };
    const fixture = TestBed.createComponent(ProjectStaffDetailPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const el: HTMLElement = fixture.nativeElement;
    buttonByText(el, 'Objects').click();
    fixture.detectChanges();

    el.querySelector<HTMLButtonElement>('.object-row__remove')!.click();
    fixture.detectChanges();
    exactButtonByText(el, 'Remove object').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Remove object and related records?');
    expect(el.textContent).toContain('Access log entries: 1');
    expect(el.textContent).toContain('Occurrence entries: 2');
    expect(el.textContent).toContain('Publication entries: 1');
    expect(exactButtonByText(el, 'Remove object and records').disabled).toBe(true);

    const reason = el.querySelector<HTMLTextAreaElement>('.cascade-remove__field textarea')!;
    reason.value = 'Object was added to the wrong project.';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(exactButtonByText(el, 'Remove object and records').disabled).toBe(false);
    exactButtonByText(el, 'Remove object and records').click();
    await fixture.whenStable();

    expect(projectService.cascadeRemovedObjects).toEqual([
      {
        id: PROJECT.id,
        objectId: 'project-object-1',
        request: {
          confirmCascade: true,
          reason: 'Object was added to the wrong project.',
        },
      },
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

function exactButtonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
    (item) => item.textContent?.trim() === label,
  );
  expect(button).not.toBeNull();
  return button!;
}
