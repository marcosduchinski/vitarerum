import { ComponentFixture, TestBed } from '@angular/core/testing';
import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { computed, signal } from '@angular/core';
import { of } from 'rxjs';

import {
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
} from '../models/collection-data-source.model';
import { COLLECTION_DATA_SOURCE_SERVICE } from '../services/collection-data-source.service';
import { CollectionDataSourcesPageComponent } from './collection-data-sources-page.component';

function makeCollection(overrides: Partial<CollectionDataSource> = {}): CollectionDataSource {
  return {
    id: 'col-zoo',
    name: 'Zoology',
    curators: [
      {
        permissionId: 'perm-1',
        name: 'Grace Curator',
        email: 'grace@museum.test',
        assignedAt: '2026-06-01T09:00:00Z',
      },
    ],
    documentCount: 1,
    manageable: true,
    ...overrides,
  };
}

function makeDocument(overrides: Partial<SourceDocument> = {}): SourceDocument {
  return {
    id: 'doc-1',
    collectionId: 'col-zoo',
    fileName: 'zoology.xlsx',
    sourceKind: 'UPLOAD',
    status: 'INDEXED',
    errorMessage: null,
    rowCount: 42,
    uploadedAt: '2026-07-01T10:00:00Z',
    indexedAt: '2026-07-01T10:00:02Z',
    ...overrides,
  };
}

class IdentityServiceStub implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>(null);
  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = signal(true).asReadonly();
  readonly isStaff = computed(() => this.session()?.group != null);

  setGroupForTest(group: GroupName): void {
    this.sessionState.set({
      accessToken: 'token',
      user: { id: 'u1', email: 'staff@museum.test', displayName: 'Staff' },
      group,
      availableGroups: [group],
    });
  }

  async signIn(credentials: LoginRequest): Promise<void> {
    this.setGroupForTest('SYS_ADMIN');
    void credentials;
  }
  signOut(): void {
    this.sessionState.set(null);
  }
  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }
  getPermissionId(): string | null {
    return null;
  }
  setGroup(group: GroupName): void {
    this.setGroupForTest(group);
  }
  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = this.sessionState();
    if (session) this.sessionState.set({ ...session, availableGroups: [...groups] });
  }
}

class ServiceStub {
  collections: CollectionDataSource[] = [makeCollection()];
  documents: SourceDocument[] = [makeDocument()];
  curatorCandidates: CuratorCandidate[] = [
    { permissionId: 'perm-1', name: 'Grace Curator', email: 'grace@museum.test' },
    { permissionId: 'perm-2', name: 'Hugo Curator', email: 'hugo@museum.test' },
  ];
  readonly uploadCalls: [string, File][] = [];
  readonly removeCalls: string[] = [];
  readonly reindexCalls: string[] = [];
  readonly createCollectionCalls: string[] = [];
  readonly updateCollectionCalls: [string, { name: string }][] = [];
  readonly removeCollectionCalls: string[] = [];
  readonly assignCuratorCalls: [string, string][] = [];
  readonly removeCuratorCalls: [string, string][] = [];

  listCollections() {
    return of(this.collections);
  }

  createCollection(name: string) {
    this.createCollectionCalls.push(name);
    return of(makeCollection({ id: 'col-new', name, curators: [], documentCount: 0 }));
  }

  updateCollection(collectionId: string, changes: { name: string }) {
    this.updateCollectionCalls.push([collectionId, changes]);
    return of(makeCollection({ id: collectionId, ...changes }));
  }

  removeCollection(collectionId: string) {
    this.removeCollectionCalls.push(collectionId);
    return of(undefined);
  }

  listDocuments(_collectionId: string) {
    return of(this.documents);
  }

  upload(collectionId: string, file: File) {
    this.uploadCalls.push([collectionId, file]);
    return of(makeDocument({ id: 'doc-new', fileName: file.name }));
  }

  remove(documentId: string) {
    this.removeCalls.push(documentId);
    return of(undefined);
  }

  reindex(documentId: string) {
    this.reindexCalls.push(documentId);
    return of(makeDocument());
  }

  listCuratorCandidates() {
    return of(this.curatorCandidates);
  }

  assignCurator(collectionId: string, permissionId: string) {
    this.assignCuratorCalls.push([collectionId, permissionId]);
    return of(null);
  }

  removeCurator(collectionId: string, permissionId: string) {
    this.removeCuratorCalls.push([collectionId, permissionId]);
    return of(undefined);
  }
}

describe('CollectionDataSourcesPageComponent', () => {
  let fixture: ComponentFixture<CollectionDataSourcesPageComponent>;
  let service: ServiceStub;
  let identity: IdentityServiceStub;

  async function setup(
    collections?: CollectionDataSource[],
    documents?: SourceDocument[],
    group: GroupName = 'COLLECTIONS_MANAGEMENT',
  ): Promise<HTMLElement> {
    service = new ServiceStub();
    if (collections) service.collections = collections;
    if (documents) service.documents = documents;
    identity = new IdentityServiceStub();
    identity.setGroupForTest(group);
    await TestBed.configureTestingModule({
      imports: [CollectionDataSourcesPageComponent],
      providers: [
        { provide: COLLECTION_DATA_SOURCE_SERVICE, useValue: service },
        { provide: IDENTITY_SERVICE, useValue: identity },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(CollectionDataSourcesPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  async function expand(el: HTMLElement): Promise<void> {
    el.querySelector<HTMLButtonElement>('.collection__header')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('lists collections with curators and file counts', async () => {
    const el = await setup();
    expect(el.textContent).toContain('Zoology');
    expect(el.textContent).toContain('Grace Curator');
    expect(el.textContent).toContain('1 file');
  });

  it('expands a collection and shows its documents with a status badge', async () => {
    const el = await setup();
    await expand(el);
    expect(el.querySelector('.documents__name')?.textContent).toContain('zoology.xlsx');
    expect(el.querySelector('.badge--indexed')?.textContent).toContain('INDEXED');
  });

  it('shows the error message for a failed document', async () => {
    const el = await setup(undefined, [
      makeDocument({ status: 'ERROR', errorMessage: 'Too many rows', rowCount: null }),
    ]);
    await expand(el);
    expect(el.querySelector('.badge--error')).not.toBeNull();
    expect(el.querySelector('.documents__error')?.textContent).toContain('Too many rows');
  });

  it('uploads the selected file to the collection', async () => {
    const el = await setup();
    await expand(el);
    const file = new File(['x'], 'new.xlsx');
    const input = el.querySelector<HTMLInputElement>('.upload input[type="file"]')!;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(service.uploadCalls).toEqual([['col-zoo', file]]);
  });

  it('asks for confirmation before deleting', async () => {
    const el = await setup();
    await expand(el);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    Array.from(el.querySelectorAll<HTMLButtonElement>('.doc-btn'))
      .find((b) => b.textContent?.includes('Delete'))!
      .click();
    await fixture.whenStable();

    expect(confirmSpy).toHaveBeenCalled();
    expect(service.removeCalls).toEqual([]);

    confirmSpy.mockReturnValue(true);
    Array.from(el.querySelectorAll<HTMLButtonElement>('.doc-btn'))
      .find((b) => b.textContent?.includes('Delete'))!
      .click();
    await fixture.whenStable();
    expect(service.removeCalls).toEqual(['doc-1']);
  });

  it('hides upload and actions for a read-only collection', async () => {
    const el = await setup([makeCollection({ manageable: false })]);
    await expand(el);
    expect(el.textContent).toContain('Read only');
    expect(el.querySelector('.upload')).toBeNull();
    expect(el.querySelector('.doc-btn')).toBeNull();
  });

  it('reindexes a document', async () => {
    const el = await setup();
    await expand(el);
    Array.from(el.querySelectorAll<HTMLButtonElement>('.doc-btn'))
      .find((b) => b.textContent?.includes('Reindex'))!
      .click();
    await fixture.whenStable();
    expect(service.reindexCalls).toEqual(['doc-1']);
  });

  describe('SYS_ADMIN catalog administration', () => {
    it('hides admin controls for non-SYS_ADMIN staff', async () => {
      const el = await setup(undefined, undefined, 'CURATORIAL');
      expect(el.querySelector('.new-collection')).toBeNull();
      expect(el.querySelector('.collection__admin-actions')).toBeNull();
    });

    it('creates a collection', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      const input = el.querySelector<HTMLInputElement>('.new-collection__input')!;
      input.value = 'Mineralogy';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      el.querySelector<HTMLButtonElement>('.new-collection__submit')!.click();
      await fixture.whenStable();

      expect(service.createCollectionCalls).toEqual(['Mineralogy']);
    });

    it('renames a collection inline', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      Array.from(el.querySelectorAll<HTMLButtonElement>('.admin-btn'))
        .find((b) => b.textContent?.includes('Rename'))!
        .click();
      fixture.detectChanges();

      const input = el.querySelector<HTMLInputElement>('.collection__name-input')!;
      input.value = 'Zoology Renamed';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      Array.from(el.querySelectorAll<HTMLButtonElement>('.admin-btn'))
        .find((b) => b.textContent?.includes('Save'))!
        .click();
      await fixture.whenStable();

      expect(service.updateCollectionCalls).toEqual([['col-zoo', { name: 'Zoology Renamed' }]]);
    });

    it('requires typing the exact collection name before removing', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      Array.from(el.querySelectorAll<HTMLButtonElement>('.admin-btn'))
        .find((b) => b.textContent?.trim() === 'Remove')!
        .click();
      fixture.detectChanges();

      expect(el.textContent).toContain('cannot be undone');
      const removeButton = Array.from(
        el.querySelectorAll<HTMLButtonElement>('.remove-confirm .admin-btn'),
      ).find((b) => b.textContent?.includes('Remove permanently'))!;
      expect(removeButton.disabled).toBe(true);

      const input = el.querySelector<HTMLInputElement>('.remove-confirm__input')!;
      input.value = 'not the name';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      expect(removeButton.disabled).toBe(true);

      input.value = 'Zoology';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      expect(removeButton.disabled).toBe(false);

      removeButton.click();
      await fixture.whenStable();
      expect(service.removeCollectionCalls).toEqual(['col-zoo']);
    });

    it('cancels the remove confirmation without calling the service', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      Array.from(el.querySelectorAll<HTMLButtonElement>('.admin-btn'))
        .find((b) => b.textContent?.trim() === 'Remove')!
        .click();
      fixture.detectChanges();

      Array.from(el.querySelectorAll<HTMLButtonElement>('.remove-confirm .admin-btn'))
        .find((b) => b.textContent?.includes('Cancel'))!
        .click();
      fixture.detectChanges();

      expect(el.querySelector('.remove-confirm')).toBeNull();
      expect(service.removeCollectionCalls).toEqual([]);
    });

    it('assigns and removes a curator from the picker', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      await expand(el);

      const select = el.querySelector<HTMLSelectElement>('.curator-admin__select')!;
      expect(select.textContent).toContain('Hugo Curator');
      expect(select.textContent).not.toContain('Grace Curator');
      select.value = 'perm-2';
      select.dispatchEvent(new Event('change'));
      fixture.detectChanges();
      el.querySelector<HTMLButtonElement>('.curator-admin__assign .admin-btn')!.click();
      await fixture.whenStable();

      expect(service.assignCuratorCalls).toEqual([['col-zoo', 'perm-2']]);

      Array.from(el.querySelectorAll<HTMLButtonElement>('.curator-admin__list .admin-btn'))
        .find((b) => b.textContent?.includes('Remove'))!
        .click();
      await fixture.whenStable();

      expect(service.removeCuratorCalls).toEqual([['col-zoo', 'perm-1']]);
    });
  });
});
