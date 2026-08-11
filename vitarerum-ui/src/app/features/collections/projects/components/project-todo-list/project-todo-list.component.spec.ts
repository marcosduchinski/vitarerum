import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';

import { ProjectTodoItem, ProjectTodoItemsResponse } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectTodoListComponent } from './project-todo-list.component';

const BASE_SESSION: IdentitySession = {
  accessToken: 'token',
  user: { id: 'u-bob', email: 'bob@example.test', displayName: 'Bob Santos' },
  group: 'CURATORIAL',
  availableGroups: ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'],
  permissions: [
    { permissionId: 'perm-bob-curatorial', group: 'CURATORIAL' },
    { permissionId: 'perm-bob-collections', group: 'COLLECTIONS_MANAGEMENT' },
  ],
};

class IdentityStub {
  readonly sessionState = signal<IdentitySession | null>(BASE_SESSION);
  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isStaff = computed(() => this.session()?.group !== 'EXTERNAL');

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

  updateAvailableGroups(): void {
    return undefined;
  }
  signIn(): Promise<void> {
    return Promise.resolve();
  }
  signOut(): void {
    return undefined;
  }
  changePassword(): Promise<void> {
    return Promise.resolve();
  }
  requestPasswordReset(): Promise<void> {
    return Promise.resolve();
  }
  confirmPasswordReset(): Promise<void> {
    return Promise.resolve();
  }
}

class ProjectTodoApiStub {
  readonly items = new Map<string, ProjectTodoItem[]>();
  calls: string[] = [];
  private nextId = 1;

  listTodoItems(projectId: string): Observable<ProjectTodoItemsResponse> {
    this.calls.push(`${projectId}::list`);
    return of({ projectId, items: this.items.get(projectId) ?? [] });
  }

  createTodoItem(projectId: string, request: { text: string }): Observable<ProjectTodoItem> {
    const item = makeItem(projectId, `todo-${this.nextId++}`, request.text);
    this.items.set(projectId, [...(this.items.get(projectId) ?? []), item]);
    return of(item);
  }

  completeTodoItem(projectId: string, itemId: string): Observable<ProjectTodoItem> {
    const item = this.replace(projectId, itemId, {
      completed: true,
      completedAt: '2026-08-11T10:00:00Z',
    });
    return of(item);
  }

  reopenTodoItem(projectId: string, itemId: string): Observable<ProjectTodoItem> {
    const item = this.replace(projectId, itemId, { completed: false, completedAt: null });
    return of(item);
  }

  deleteTodoItem(projectId: string, itemId: string): Observable<void> {
    this.items.set(
      projectId,
      (this.items.get(projectId) ?? []).filter((item) => item.id !== itemId),
    );
    return of(void 0);
  }

  private replace(
    projectId: string,
    itemId: string,
    patch: Partial<ProjectTodoItem>,
  ): ProjectTodoItem {
    const items = this.items.get(projectId) ?? [];
    const item = { ...items.find((candidate) => candidate.id === itemId)!, ...patch };
    this.items.set(
      projectId,
      items.map((candidate) => (candidate.id === itemId ? item : candidate)),
    );
    return item;
  }
}

describe('ProjectTodoListComponent', () => {
  let fixture: ComponentFixture<ProjectTodoListComponent>;
  let api: ProjectTodoApiStub;
  let identity: IdentityStub;

  beforeEach(async () => {
    api = new ProjectTodoApiStub();
    identity = new IdentityStub();
    api.items.set('project-1', [makeItem('project-1', 'todo-existing', 'Confirm labels')]);

    await TestBed.configureTestingModule({
      imports: [ProjectTodoListComponent],
      providers: [
        { provide: PROJECT_API_SERVICE, useValue: api },
        { provide: IDENTITY_SERVICE, useValue: identity },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProjectTodoListComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('loads saved items and prevents blank items', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const addButton = compiled.querySelector<HTMLButtonElement>('button[type="submit"]')!;

    expect(compiled.textContent).toContain('Confirm labels');
    expect(compiled.textContent).toContain('0 of 1 completed');
    expect(addButton.disabled).toBe(true);
  });

  it('adds, checks, unchecks, and removes items through the API', async () => {
    const compiled = fixture.nativeElement as HTMLElement;
    await addItem(fixture, 'Schedule handling review');

    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(2);
    expect(compiled.textContent).toContain('Schedule handling review');

    const firstCheckbox = compiled.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    firstCheckbox.checked = true;
    firstCheckbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('1 of 2 completed');

    firstCheckbox.checked = false;
    firstCheckbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('0 of 2 completed');

    compiled
      .querySelector<HTMLButtonElement>('[aria-label="Remove Schedule handling review"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(1);
    expect(compiled.textContent).not.toContain('Schedule handling review');
  });

  it('reloads when the project changes', async () => {
    api.items.set('project-2', [makeItem('project-2', 'todo-project-2', 'Review loan conditions')]);

    fixture.componentRef.setInput('projectId', 'project-2');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Review loan conditions');
    expect(compiled.textContent).not.toContain('Confirm labels');
  });

  it('reloads when the active staff profile changes', async () => {
    identity.setGroup('COLLECTIONS_MANAGEMENT');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.calls.filter((call) => call === 'project-1::list')).toHaveLength(2);
  });
});

function makeItem(projectId: string, id: string, text: string): ProjectTodoItem {
  return {
    id,
    projectId,
    text,
    completed: false,
    createdAt: '2026-08-11T09:00:00Z',
    updatedAt: '2026-08-11T09:00:00Z',
    completedAt: null,
    position: 10,
  };
}

async function addItem(
  fixture: ComponentFixture<ProjectTodoListComponent>,
  text: string,
): Promise<void> {
  const compiled = fixture.nativeElement as HTMLElement;
  const input = compiled.querySelector<HTMLInputElement>('#project-todo-input')!;
  const form = compiled.querySelector<HTMLFormElement>('form')!;

  input.value = text;
  input.dispatchEvent(new Event('input'));
  fixture.detectChanges();
  form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}
