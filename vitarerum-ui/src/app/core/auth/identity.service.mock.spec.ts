import { IdentityServiceMock } from './identity.service.mock';
import { clearSession } from './session-storage.util';

function signIn(service: IdentityServiceMock, email: string): Promise<void> {
  return service.signIn({ email, password: 'vita2026' });
}

describe('IdentityServiceMock', () => {
  beforeEach(() => {
    clearSession();
  });

  afterEach(() => {
    clearSession();
  });

  it('updates authentication signals when signing in and out', async () => {
    const service = new IdentityServiceMock();

    expect(service.isAuthenticated()).toBe(false);
    expect(service.session()).toBeNull();
    expect(service.getAccessToken()).toBeNull();

    await signIn(service, 'learner@example.com');

    expect(service.isAuthenticated()).toBe(true);
    expect(service.session()?.user.email).toBe('learner@example.com');
    expect(service.getAccessToken()).toBe('mock-access-token');

    service.signOut();

    expect(service.isAuthenticated()).toBe(false);
    expect(service.session()).toBeNull();
  });

  it('rejects an invalid password without changing the session', async () => {
    const service = new IdentityServiceMock();

    await expect(
      service.signIn({ email: 'alice@ext.example.com', password: 'incorrect' }),
    ).rejects.toThrow('Invalid mock credentials');
    expect(service.session()).toBeNull();

    await signIn(service, 'alice@ext.example.com');
    const existingSession = service.session();

    await expect(
      service.signIn({ email: 'bob@collections.example.com', password: 'incorrect' }),
    ).rejects.toThrow('Invalid mock credentials');
    expect(service.session()).toEqual(existingSession);
  });

  it('sets the correct group and name for known mock accounts', async () => {
    const service = new IdentityServiceMock();

    await signIn(service, 'alice@ext.example.com');
    expect(service.session()?.group).toBe('EXTERNAL');
    expect(service.session()?.user.displayName).toBe('Alice Ferreira');
    expect(service.session()?.availableGroups).toEqual(['EXTERNAL']);

    await signIn(service, 'bob@collections.example.com');
    expect(service.session()?.group).toBe('COLLECTIONS_MANAGEMENT');
    expect(service.session()?.availableGroups).toEqual(['COLLECTIONS_MANAGEMENT']);

    await signIn(service, 'eve@admin.example.com');
    expect(service.session()?.group).toBe('SYS_ADMIN');
    expect(service.session()?.availableGroups).toEqual(['SYS_ADMIN']);
  });

  it('defaults unknown emails to EXTERNAL group', async () => {
    const service = new IdentityServiceMock();
    await signIn(service, 'stranger@example.com');
    expect(service.session()?.group).toBe('EXTERNAL');
    expect(service.session()?.availableGroups).toEqual(['EXTERNAL']);
  });

  it('exposes a permission id for the active group', async () => {
    const service = new IdentityServiceMock();
    expect(service.getPermissionId()).toBeNull();

    await signIn(service, 'alice@ext.example.com');
    expect(service.getPermissionId()).toBe('perm-alice');

    await signIn(service, 'greg@collections.example.com');
    expect(service.getPermissionId()).toBe('perm-greg');
  });

  it('rehydrates the mock session for new tabs and page reloads', async () => {
    const service = new IdentityServiceMock();

    await signIn(service, 'greg@collections.example.com');

    const rehydrated = new IdentityServiceMock();

    expect(rehydrated.isAuthenticated()).toBe(true);
    expect(rehydrated.session()?.user.email).toBe('greg@collections.example.com');
    expect(rehydrated.getPermissionId()).toBe('perm-greg');
  });

  it('setGroup succeeds when the group is in availableGroups', async () => {
    const service = new IdentityServiceMock();
    await signIn(service, 'alice@ext.example.com');
    service.setGroup('EXTERNAL');
    expect(service.session()?.group).toBe('EXTERNAL');
  });

  it('setGroup is ignored when the group is not in availableGroups', async () => {
    const service = new IdentityServiceMock();
    await signIn(service, 'alice@ext.example.com'); // only EXTERNAL
    service.setGroup('SYS_ADMIN'); // not allowed
    expect(service.session()?.group).toBe('EXTERNAL'); // unchanged
  });

  it('multi-group user can switch groups and the permission id follows', async () => {
    const service = new IdentityServiceMock();
    await signIn(service, 'fran@staff.example.com');

    expect(service.session()?.availableGroups).toEqual([
      'COLLECTIONS_MANAGEMENT',
      'CURATORIAL',
      'DIRECTION',
    ]);
    expect(service.session()?.group).toBe('COLLECTIONS_MANAGEMENT'); // first group on sign-in
    expect(service.getPermissionId()).toBe('perm-fran-collections');

    service.setGroup('CURATORIAL');
    expect(service.session()?.group).toBe('CURATORIAL');
    expect(service.getPermissionId()).toBe('perm-fran-curatorial');

    service.setGroup('DIRECTION');
    expect(service.session()?.group).toBe('DIRECTION');
    expect(service.getPermissionId()).toBe('perm-fran-direction');

    // Cannot switch to a group outside their list.
    service.setGroup('SYS_ADMIN');
    expect(service.session()?.group).toBe('DIRECTION'); // unchanged
  });
});
