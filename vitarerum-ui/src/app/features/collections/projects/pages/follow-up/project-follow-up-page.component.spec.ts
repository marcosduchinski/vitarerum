import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import {
  CollectionUseProjectDetail,
  CreateFollowUpProjectRequest,
} from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectFollowUpPageComponent } from './project-follow-up-page.component';

let currentProject: CollectionUseProjectDetail;

const PROJECT: CollectionUseProjectDetail = {
  id: 'proj-12',
  referenceNumber: 'CUP-DAF9DC7D',
  title: 'Atlantic forest zoology specimens',
  purpose: 'Comparative study of specimen records.',
  type: 'IN_SITU_VISIT',
  status: 'COMPLETED',
  result: 'COMPLETED',
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
  objects: [
    {
      id: 'object-1',
      inventoryNumber: 'INV-001',
      displayTitle: 'Book of Hours',
      objectName: 'Manuscript',
      briefDescriptionSnapshot: null,
      category: 'manuscript',
      description: 'Illuminated manuscript.',
    },
    {
      id: 'object-2',
      inventoryNumber: 'INV-002',
      displayTitle: null,
      objectName: 'Specimen drawer',
      briefDescriptionSnapshot: null,
      category: 'zoology',
      description: 'Drawer with specimens.',
    },
  ],
  staffContext: null,
};

class ProjectApiServiceStub {
  readonly createCalls: { projectId: string; request: CreateFollowUpProjectRequest }[] = [];

  getProject() {
    return of(currentProject);
  }

  createFollowUpProject(projectId: string, request: CreateFollowUpProjectRequest) {
    this.createCalls.push({ projectId, request });
    return of({
      ...currentProject,
      id: 'proj-follow-up',
      referenceNumber: 'CUP-2026-0002',
      status: 'CREATED',
      result: null,
      originProjectId: projectId,
      proposal: null,
    } satisfies CollectionUseProjectDetail);
  }
}

describe('ProjectFollowUpPageComponent', () => {
  let projectService: ProjectApiServiceStub;
  let router: Router;

  async function configure(section?: string): Promise<void> {
    currentProject = { ...PROJECT, objects: [...(PROJECT.objects ?? [])] };
    projectService = new ProjectApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProjectFollowUpPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROJECT_API_SERVICE, useValue: projectService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap(section ? { section } : {}),
            },
          },
        },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  }

  it('loads the origin project and submits selected objects', async () => {
    await configure('curatorial');
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectFollowUpPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('CUP-DAF9DC7D');
    setInput(fixture.nativeElement, '#follow-up-begin-date', '2027-01-10');
    setInput(fixture.nativeElement, '#follow-up-end-date', '2027-01-20');
    setInput(fixture.nativeElement, '#follow-up-note', 'Second campaign.');
    checkboxFor(fixture.nativeElement, 'Book of Hours').click();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Create follow-up').click();
    await fixture.whenStable();

    expect(projectService.createCalls).toEqual([
      {
        projectId: PROJECT.id,
        request: {
          title: 'Atlantic forest zoology specimens',
          purpose: 'Comparative study of specimen records.',
          beginDate: '2027-01-10',
          endDate: '2027-01-20',
          note: 'Second campaign.',
          objectIds: ['object-2'],
        },
      },
    ]);
    // The section comes from the `?section=` query param (see `configure`
    // above), carried through from wherever "Create follow-up project" was
    // triggered — it must not be hardcoded to 'collections'.
    expect(navigate).toHaveBeenCalledWith([
      '/p/collections/projects',
      'curatorial',
      'proj-follow-up',
    ]);
  });

  it('defaults the section to collections when none is provided', async () => {
    await configure();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProjectFollowUpPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    setInput(fixture.nativeElement, '#follow-up-begin-date', '2027-01-10');
    setInput(fixture.nativeElement, '#follow-up-end-date', '2027-01-20');
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Create follow-up').click();
    await fixture.whenStable();

    expect(navigate).toHaveBeenCalledWith([
      '/p/collections/projects',
      'collections',
      'proj-follow-up',
    ]);
  });

  it('blocks creation for non-completed projects', async () => {
    await configure();
    currentProject = { ...PROJECT, status: 'IN_PROGRESS', result: null };
    const fixture = TestBed.createComponent(ProjectFollowUpPageComponent);
    fixture.componentRef.setInput('id', PROJECT.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'Only completed projects can create follow-ups.',
    );
    expect(buttonByText(fixture.nativeElement, 'Create follow-up').disabled).toBe(true);
  });
});

function setInput(root: HTMLElement, selector: string, value: string): void {
  const input = root.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
  expect(input).not.toBeNull();
  input!.value = value;
  input!.dispatchEvent(new Event('input'));
}

function checkboxFor(root: HTMLElement, label: string): HTMLInputElement {
  const checkbox = Array.from(root.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')).find(
    (input) => input.closest('.object-row')?.textContent?.includes(label),
  );
  expect(checkbox).not.toBeNull();
  return checkbox!;
}

function buttonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).not.toBeNull();
  return button!;
}
