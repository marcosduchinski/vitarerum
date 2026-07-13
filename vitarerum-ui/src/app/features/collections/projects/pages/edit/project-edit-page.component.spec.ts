import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { CollectionUseProjectDetail, UpdateProjectRequest } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectEditPageComponent } from './project-edit-page.component';

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
    assignedTo: null,
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

class ProjectApiServiceStub {
  project = structuredClone(PROJECT);
  readonly updateCalls: { projectId: string; request: UpdateProjectRequest }[] = [];
  updateError: HttpErrorResponse | null = null;

  getProject() {
    return of(this.project);
  }

  updateProject(projectId: string, request: UpdateProjectRequest) {
    this.updateCalls.push({ projectId, request });
    if (this.updateError) return throwError(() => this.updateError);

    const updated: CollectionUseProjectDetail = {
      ...this.project,
      title: request.title === undefined ? this.project.title : (request.title ?? ''),
      purpose: request.purpose === undefined ? this.project.purpose : (request.purpose ?? ''),
      beginDate:
        request.beginDate === undefined ? this.project.beginDate : (request.beginDate ?? ''),
      endDate: request.endDate === undefined ? this.project.endDate : (request.endDate ?? ''),
    };
    return of(updated);
  }
}

describe('ProjectEditPageComponent', () => {
  let fixture: ComponentFixture<ProjectEditPageComponent>;
  let service: ProjectApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    service = new ProjectApiServiceStub();
    await TestBed.configureTestingModule({
      imports: [ProjectEditPageComponent],
      providers: [provideRouter([]), { provide: PROJECT_API_SERVICE, useValue: service }],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  async function render(): Promise<HTMLElement> {
    fixture = TestBed.createComponent(ProjectEditPageComponent);
    fixture.componentRef.setInput('id', 'proj-12');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('loads the editable project metadata into the form', async () => {
    const compiled = await render();

    expect(input(compiled, 'project-edit-title').value).toBe(
      'Atlantic forest zoology specimens',
    );
    expect(textarea(compiled, 'project-edit-purpose').value).toBe(
      'Comparative study of specimen records.',
    );
    expect(input(compiled, 'project-edit-begin-date').value).toBe('2026-07-01');
    expect(input(compiled, 'project-edit-end-date').value).toBe('2026-12-31');
    expect(button(compiled, 'Save changes').disabled).toBe(true);
  });

  it('sends only changed fields and returns to the project detail route', async () => {
    const compiled = await render();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    change(input(compiled, 'project-edit-title'), 'Revised specimens survey');
    fixture.detectChanges();
    button(compiled, 'Save changes').click();
    await fixture.whenStable();

    expect(service.updateCalls).toEqual([
      { projectId: 'proj-12', request: { title: 'Revised specimens survey' } },
    ]);
    expect(navigate).toHaveBeenCalledWith(['/p/collections/projects', 'collections', 'proj-12']);
  });

  it('shows an inline error and blocks save when end date precedes begin date', async () => {
    const compiled = await render();

    change(input(compiled, 'project-edit-end-date'), '2026-01-01');
    fixture.detectChanges();

    expect(compiled.textContent).toContain('End date cannot precede begin date.');
    expect(button(compiled, 'Save changes').disabled).toBe(true);
    expect(service.updateCalls).toEqual([]);
  });

  it('blocks terminal projects and keeps API failures visible on the page', async () => {
    service.project = { ...structuredClone(PROJECT), status: 'COMPLETED' };
    let compiled = await render();

    expect(compiled.textContent).toContain('Completed or cancelled projects cannot be edited.');
    expect(compiled.querySelector('form button[type="submit"]')?.hasAttribute('disabled')).toBe(
      true,
    );

    fixture.destroy();
    service.project = structuredClone(PROJECT);
    service.updateError = new HttpErrorResponse({
      status: 422,
      error: { message: 'endDate must be after beginDate' },
    });
    compiled = await render();
    change(input(compiled, 'project-edit-title'), 'Another title');
    fixture.detectChanges();
    button(compiled, 'Save changes').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('endDate must be after beginDate');
    expect(input(compiled, 'project-edit-title').value).toBe('Another title');
  });
});

function input(root: HTMLElement, id: string): HTMLInputElement {
  return root.querySelector<HTMLInputElement>(`#${id}`)!;
}

function textarea(root: HTMLElement, id: string): HTMLTextAreaElement {
  return root.querySelector<HTMLTextAreaElement>(`#${id}`)!;
}

function button(root: HTMLElement, text: string): HTMLButtonElement {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((candidate) =>
    candidate.textContent?.includes(text),
  )!;
}

function change(element: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}
