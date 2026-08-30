import { computed, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import {
  ProjectTodoItem,
  ProjectTodoPostitsResponse,
} from '@features/collections/projects/models/project.model';
import { PROJECT_API_SERVICE } from '@features/collections/projects/services/project-api.service';

import { DashboardComponent } from './dashboard.component';

const SESSION: IdentitySession = {
  accessToken: 'token',
  user: { id: 'user-bob', email: 'bob@example.test', displayName: 'Bob Santos' },
  group: 'CURATORIAL',
  availableGroups: ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'],
  permissions: [
    { permissionId: 'perm-bob-curatorial', group: 'CURATORIAL' },
    { permissionId: 'perm-bob-collections', group: 'COLLECTIONS_MANAGEMENT' },
  ],
};

class IdentityStub {
  readonly sessionState = signal<IdentitySession | null>(SESSION);
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

class ProjectApiStub {
  items: ProjectTodoPostitsResponse['items'] = [
    {
      id: 'todo-1',
      projectId: 'project-1',
      projectReferenceNumber: 'CUP-20260811-0001',
      projectTitle: 'Condition report',
      projectStatus: 'IN_PROGRESS',
      text: 'Confirm handling conditions',
      completed: false,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:05:00Z',
      completedAt: null,
      position: 10,
    },
  ];

  listMyTodoPostits(): Observable<ProjectTodoPostitsResponse> {
    return of({ items: this.items });
  }

  completeTodoItem(projectId: string, itemId: string): Observable<ProjectTodoItem> {
    this.items = this.items.filter((item) => item.id !== itemId || item.projectId !== projectId);
    return of({
      id: itemId,
      projectId,
      text: 'Confirm handling conditions',
      completed: true,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:10:00Z',
      completedAt: '2026-08-11T10:10:00Z',
      position: 10,
    });
  }
}

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityStub },
        { provide: PROJECT_API_SERVICE, useClass: ProjectApiStub },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
  });

  it('renders current staff TODOs as post-its', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('My post-its');
    expect(compiled.textContent).toContain('CUP-20260811-0001');
    expect(compiled.textContent).toContain('Condition report');
    expect(compiled.textContent).toContain('Confirm handling conditions');
    // A post-it deep-links into the project's TODO tab, where it came from.
    expect(compiled.querySelector('a')?.getAttribute('href')).toBe(
      '/p/collections/projects/curatorial/project-1?tab=todo',
    );
  });

  it('removes a post-it after completing it from the dashboard', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.postit__complete') as HTMLButtonElement;
    button.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'No open TODOs for this staff profile.',
    );
  });
});
