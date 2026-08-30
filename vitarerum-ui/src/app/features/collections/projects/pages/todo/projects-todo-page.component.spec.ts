import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Page } from '@shared/models/page.model';

import {
  CollectionUseProjectSummary,
  CreateProjectTodoItemRequest,
  ProjectListQuery,
  ProjectTodoPostit,
  ProjectTodoPostitsQuery,
  ProjectTodoPostitsResponse,
} from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectsTodoPageComponent } from './projects-todo-page.component';

function project(
  id: string,
  reference: string,
  status: CollectionUseProjectSummary['status'],
): CollectionUseProjectSummary {
  return {
    id,
    referenceNumber: reference,
    title: `Project ${reference}`,
    purpose: 'Collection-use work.',
    type: 'IN_SITU_VISIT',
    status,
    result: null,
    beginDate: '2026-06-10',
    endDate: '2026-06-20',
    requestedBy: {
      permissionId: 'permission-external',
      user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
      group: 'EXTERNAL',
    },
  } as CollectionUseProjectSummary;
}

const ACTIVE = project('project-1', 'VR-2026-001', 'IN_PROGRESS');
const CREATED = project('project-2', 'VR-2026-002', 'CREATED');
const CLOSED = project('project-3', 'VR-2026-003', 'COMPLETED');

function postit(id: string, projectId: string, reference: string, text: string): ProjectTodoPostit {
  return {
    id,
    projectId,
    projectReferenceNumber: reference,
    projectTitle: `Project ${reference}`,
    projectStatus: 'IN_PROGRESS',
    text,
    completed: false,
    createdAt: '2026-08-11T10:00:00Z',
    updatedAt: '2026-08-11T10:05:00Z',
    completedAt: null,
    position: 10,
  };
}

class ProjectApiServiceStub {
  readonly todoQueries: ProjectTodoPostitsQuery[] = [];
  readonly projectQueries: ProjectListQuery[] = [];
  readonly created: { projectId: string; text: string }[] = [];

  postits: ProjectTodoPostit[] = [
    postit('todo-1', 'project-1', 'VR-2026-001', 'Confirm handling conditions'),
    postit('todo-2', 'project-1', 'VR-2026-001', 'Book the reading room'),
    postit('todo-3', 'project-2', 'VR-2026-002', 'Chase the loan agreement'),
  ];

  listMyTodoPostits(query: ProjectTodoPostitsQuery = {}) {
    this.todoQueries.push(query);
    const items = query.projectId
      ? this.postits.filter((item) => item.projectId === query.projectId)
      : this.postits;
    const page = query.page ?? 0;
    const size = query.size ?? 20;
    return of<ProjectTodoPostitsResponse>({
      content: items.slice(page * size, page * size + size),
      page,
      size,
      totalElements: items.length,
      totalPages: Math.ceil(items.length / size),
    });
  }

  deleteTodoItem(projectId: string, itemId: string) {
    this.postits = this.postits.filter((item) => item.id !== itemId);
    return of(void 0);
  }

  listProjects(query: ProjectListQuery = {}) {
    this.projectQueries.push(query);
    const all = [ACTIVE, CREATED, CLOSED];
    const content = all.filter((item) => !query.status || item.status === query.status);
    return of<Page<CollectionUseProjectSummary>>({
      content,
      page: 0,
      size: query.size ?? 20,
      totalElements: content.length,
      totalPages: 1,
    });
  }

  createTodoItem(projectId: string, request: CreateProjectTodoItemRequest) {
    this.created.push({ projectId, text: request.text });
    return of(postit('todo-new', projectId, 'VR-2026-001', request.text));
  }
}

describe('ProjectsTodoPageComponent', () => {
  let projectService: ProjectApiServiceStub;

  beforeEach(async () => {
    projectService = new ProjectApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectsTodoPageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectService },
      ],
    }).compileComponents();

    const identity = TestBed.inject(IDENTITY_SERVICE) as IdentityServiceMock;
    await identity.signIn({ email: 'carol@curatorial.example.com', password: 'vita2026' });
  });

  async function render() {
    const fixture = TestBed.createComponent(ProjectsTodoPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('asks the server for a project-ordered page of open items', async () => {
    await render();

    expect(projectService.todoQueries.at(-1)).toEqual({
      completed: false,
      projectId: undefined,
      sort: 'project',
      page: 0,
      size: 20,
    });
  });

  it('groups items under their project', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    const groups = compiled.querySelectorAll('.todo-group');
    expect(groups.length).toBe(2);
    expect(groups[0].textContent).toContain('VR-2026-001');
    expect(groups[0].querySelectorAll('.todo-item').length).toBe(2);
    expect(groups[1].textContent).toContain('VR-2026-002');
    expect(groups[1].querySelectorAll('.todo-item').length).toBe(1);
  });

  it('links each group heading to that project TODO tab', async () => {
    const fixture = await render();
    const link = (fixture.nativeElement as HTMLElement).querySelector('.todo-group__project');

    expect(link?.getAttribute('href')).toBe(
      '/p/collections/projects/curatorial/project-1?tab=todo',
    );
  });

  it('cannot add an item before a project is chosen', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const input = compiled.querySelector('#todo-page-input') as HTMLInputElement;

    input.value = 'Draft the condition report';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const submit = compiled.querySelector('.todo-compose__controls button') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(compiled.textContent).toContain('Every item belongs to a project');
  });

  it('offers every project in the picker, whatever its status', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('.picker__current') as HTMLButtonElement).click();
    fixture.detectChanges();
    (compiled.querySelector('.picker__search button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    // No status filter is sent: a completed or cancelled project can still
    // take a follow-up item.
    expect(projectService.projectQueries.length).toBe(1);
    expect(projectService.projectQueries[0].status).toBeUndefined();

    const results = compiled.querySelector('.picker__results') as HTMLElement;
    expect(results.querySelectorAll('button').length).toBe(3);
    expect(results.textContent).toContain('VR-2026-003');
    expect(results.textContent).toContain('Completed');
  });

  it('adds an item to the project chosen in the picker', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('.picker__current') as HTMLButtonElement).click();
    fixture.detectChanges();
    (compiled.querySelector('.picker__search button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    (compiled.querySelector('.picker__results button') as HTMLButtonElement).click();
    fixture.detectChanges();

    const input = compiled.querySelector('#todo-page-input') as HTMLInputElement;
    input.value = 'Draft the condition report';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    (compiled.querySelector('.todo-compose__controls button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.created).toEqual([
      { projectId: 'project-1', text: 'Draft the condition report' },
    ]);
  });

  it('narrows the list to the chosen project on request', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('.picker__current') as HTMLButtonElement).click();
    fixture.detectChanges();
    (compiled.querySelector('.picker__search button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    (compiled.querySelector('.picker__results button') as HTMLButtonElement).click();
    fixture.detectChanges();

    const scope = compiled.querySelector('.todo-filters__scope input') as HTMLInputElement;
    scope.checked = true;
    scope.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.todoQueries.at(-1)?.projectId).toBe('project-1');
    expect(compiled.querySelectorAll('.todo-group').length).toBe(1);
  });

  it('does not submit the compose form when searching in the picker', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    // A nested <form> would make the picker's search button submit the compose
    // form instead, silently creating an item.
    expect(compiled.querySelectorAll('.picker form').length).toBe(0);

    const input = compiled.querySelector('#todo-page-input') as HTMLInputElement;
    input.value = 'Draft the condition report';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    (compiled.querySelector('.picker__current') as HTMLButtonElement).click();
    fixture.detectChanges();
    (compiled.querySelector('.picker__search button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.created).toEqual([]);
  });

  it('labels picker results with a readable status, not the raw enum', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('.picker__current') as HTMLButtonElement).click();
    fixture.detectChanges();
    (compiled.querySelector('.picker__search button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    const results = compiled.querySelector('.picker__results') as HTMLElement;
    expect(results.textContent).toContain('In progress');
    expect(results.textContent).not.toContain('IN_PROGRESS');
    // The visible title is ellipsised, so the full text lives on the tooltip.
    expect(results.querySelector('button')?.getAttribute('title')).toContain('Project VR-2026-001');
  });

  it('steps back a page when the last item on it is removed', async () => {
    // 21 items over a page size of 20: page 1 holds exactly one item, so
    // removing it used to strand the view on an empty page.
    projectService.postits = Array.from({ length: 21 }, (_, index) =>
      postit(`todo-${index + 1}`, 'project-1', 'VR-2026-001', `Item ${index + 1}`),
    );
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    (compiled.querySelector('[aria-label="Next page"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(projectService.todoQueries.at(-1)?.page).toBe(1);
    expect(compiled.querySelectorAll('.todo-item').length).toBe(1);

    (compiled.querySelector('.todo-item__remove') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(projectService.todoQueries.at(-1)?.page).toBe(0);
    expect(compiled.querySelectorAll('.todo-item').length).toBe(20);
  });

  it('asks for completed items when the filter changes', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const buttons = compiled.querySelectorAll('.todo-filters__group button');

    (buttons[1] as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(projectService.todoQueries.at(-1)?.completed).toBe(true);

    (buttons[2] as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(projectService.todoQueries.at(-1)?.completed).toBeUndefined();
  });
});
