import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { UserManagementService } from './user-management.service';

describe('UserManagementService', () => {
  let service: UserManagementService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/' },
        UserManagementService,
      ],
    });

    service = TestBed.inject(UserManagementService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists users with structured query parameters', () => {
    service.listUsers({ groupId: 'group-1', search: 'ana', page: 1, size: 10 }).subscribe();

    const request = http.expectOne('https://api.example.test/users?groupId=group-1&search=ana&page=1&size=10');

    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('groupId')).toBe('group-1');
    expect(request.request.params.get('search')).toBe('ana');
    request.flush({ content: [], page: 1, size: 10, totalElements: 0, totalPages: 0 });
  });

  it('creates a user', () => {
    const payload = { name: 'Ana', email: 'ana@example.test', password: 'secret123' };
    service.createUser(payload).subscribe();

    const request = http.expectOne('https://api.example.test/users');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush({ id: 'user-1', name: 'Ana', email: 'ana@example.test', permissions: [] });
  });

  it('assigns and revokes group membership', () => {
    service.assignGroup('user-1', 'group-1').subscribe();

    const assignRequest = http.expectOne('https://api.example.test/users/user-1/groups/group-1');

    expect(assignRequest.request.method).toBe('POST');
    expect(assignRequest.request.body).toBeNull();
    assignRequest.flush({
      permissionId: 'permission-1',
      user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
      group: { id: 'group-1', name: 'CURATORIAL' },
    });

    service.revokeGroup('user-1', 'group-1').subscribe();

    const revokeRequest = http.expectOne('https://api.example.test/users/user-1/groups/group-1');

    expect(revokeRequest.request.method).toBe('DELETE');
    revokeRequest.flush(null);
  });

  it('fetches a single user by id', () => {
    service.getUser('user-1').subscribe();

    const request = http.expectOne('https://api.example.test/users/user-1');

    expect(request.request.method).toBe('GET');
    request.flush({ id: 'user-1', name: 'Ana', email: 'ana@example.test', permissions: [] });
  });

  it('updates user name and status', () => {
    service.updateUser('user-1', { name: 'Ana Maria' }).subscribe();

    const updateRequest = http.expectOne('https://api.example.test/users/user-1');

    expect(updateRequest.request.method).toBe('PUT');
    expect(updateRequest.request.body).toEqual({ name: 'Ana Maria' });
    updateRequest.flush({
      id: 'user-1',
      name: 'Ana Maria',
      email: 'ana@example.test',
      status: 'ACTIVE',
      permissions: [],
    });

    service.disableUser('user-1').subscribe();

    const disableRequest = http.expectOne('https://api.example.test/users/user-1/disable');

    expect(disableRequest.request.method).toBe('POST');
    expect(disableRequest.request.body).toBeNull();
    disableRequest.flush({
      id: 'user-1',
      name: 'Ana Maria',
      email: 'ana@example.test',
      status: 'DISABLED',
      permissions: [],
    });

    service.enableUser('user-1').subscribe();

    const enableRequest = http.expectOne('https://api.example.test/users/user-1/enable');

    expect(enableRequest.request.method).toBe('POST');
    expect(enableRequest.request.body).toBeNull();
    enableRequest.flush({
      id: 'user-1',
      name: 'Ana Maria',
      email: 'ana@example.test',
      status: 'ACTIVE',
      permissions: [],
    });
  });

  it('requests an administrative password reset', () => {
    service.requestPasswordReset('user-1').subscribe();

    const request = http.expectOne('https://api.example.test/users/user-1/password-reset');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    request.flush(null);
  });

  it('lists permissions for a user', () => {
    service.listUserPermissions('user-1').subscribe();

    const request = http.expectOne('https://api.example.test/users/user-1/permissions');

    expect(request.request.method).toBe('GET');
    request.flush({
      userId: 'user-1',
      permissions: [{ permissionId: 'perm-1', group: { id: 'g-1', name: 'CURATORIAL' } }],
    });
  });

  it('lists groups and group users', () => {
    service.listGroups().subscribe();

    const groupsRequest = http.expectOne('https://api.example.test/groups');

    expect(groupsRequest.request.method).toBe('GET');
    groupsRequest.flush({ groups: [] });

    service.listGroupUsers('group-1', { page: 2, size: 5 }).subscribe();

    const usersRequest = http.expectOne('https://api.example.test/groups/group-1/users?page=2&size=5');

    expect(usersRequest.request.method).toBe('GET');
    usersRequest.flush({
      group: { id: 'group-1', name: 'CURATORIAL' },
      content: [],
      page: 2,
      size: 5,
      totalElements: 0,
      totalPages: 0,
    });
  });
});
