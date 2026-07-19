import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { computed, signal } from '@angular/core';
import { of, throwError } from 'rxjs';

import {
  CollectionArea,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
} from '../models/collection-data-source.model';
import { COLLECTION_DATA_SOURCE_SERVICE } from '../services/collection-data-source.service';
import { CollectionDataSourcesPageComponent } from './collection-data-sources-page.component';

function makeArea(overrides: Partial<CollectionArea> = {}): CollectionArea {
  return {
    id: 'area-nat-hist',
    name: 'Natural History',
    collectionCount: 1,
    ...overrides,
  };
}

function makeCollection(overrides: Partial<CollectionDataSource> = {}): CollectionDataSource {
  return {
    id: 'col-zoo',
    areaId: 'area-nat-hist',
    areaName: 'Natural History',
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
    objectMapping: null,
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

class ServiceStub {
  collections: CollectionDataSource[] = [makeCollection()];
  documents: SourceDocument[] = [makeDocument()];
  areas: CollectionArea[] = [makeArea(), makeArea({ id: 'area-media', name: 'Documentation & Media', collectionCount: 0 })];
  curatorCandidates: CuratorCandidate[] = [
    { permissionId: 'perm-1', name: 'Grace Curator', email: 'grace@museum.test' },
    { permissionId: 'perm-2', name: 'Hugo Curator', email: 'hugo@museum.test' },
  ];
  readonly uploadCalls: [string, File][] = [];
  readonly previewDocumentColumnsCalls: [string, File][] = [];
  readonly removeCalls: string[] = [];
  readonly reindexCalls: string[] = [];
  readonly listDocumentColumnsCalls: string[] = [];
  readonly updateObjectMappingCalls: unknown[] = [];
  readonly createCollectionCalls: [string, string][] = [];
  readonly updateCollectionCalls: [string, { name: string }][] = [];
  readonly removeCollectionCalls: string[] = [];
  readonly assignCuratorCalls: [string, string][] = [];
  readonly removeCuratorCalls: [string, string][] = [];
  readonly createAreaCalls: string[] = [];
  readonly updateAreaCalls: [string, string][] = [];
  readonly removeAreaCalls: string[] = [];
  readonly moveCollectionToAreaCalls: [string, string][] = [];

  listCollections() {
    return of(this.collections);
  }

  createCollection(name: string, areaId: string) {
    this.createCollectionCalls.push([name, areaId]);
    const area = this.areas.find((a) => a.id === areaId);
    return of(
      makeCollection({
        id: 'col-new',
        name,
        areaId,
        areaName: area?.name ?? '',
        curators: [],
        documentCount: 0,
      }),
    );
  }

  updateCollection(collectionId: string, changes: { name: string }) {
    this.updateCollectionCalls.push([collectionId, changes]);
    return of(makeCollection({ id: collectionId, ...changes }));
  }

  removeCollection(collectionId: string) {
    this.removeCollectionCalls.push(collectionId);
    return of(undefined);
  }

  listDocuments() {
    return of(this.documents);
  }

  listDocumentColumns(documentId: string) {
    this.listDocumentColumnsCalls.push(documentId);
    return of(['Inventory No', 'Name', 'Description', 'Notes']);
  }

  updateObjectMapping(documentId: string, request: unknown) {
    this.updateObjectMappingCalls.push([documentId, request]);
    return of(
      makeDocument({
        id: documentId,
        objectMapping: request as SourceDocument['objectMapping'],
      }),
    );
  }

  previewDocumentColumns(collectionId: string, file: File) {
    this.previewDocumentColumnsCalls.push([collectionId, file]);
    return of(['Inventory No', 'Name', 'Description', 'Notes']);
  }

  upload(collectionId: string, file: File, objectMapping: SourceDocument['objectMapping']) {
    this.uploadCalls.push([collectionId, file]);
    return of(makeDocument({ id: 'doc-new', fileName: file.name, objectMapping }));
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

  listAreas() {
    return of(this.areas);
  }

  createArea(name: string) {
    this.createAreaCalls.push(name);
    const area = makeArea({ id: 'area-new', name, collectionCount: 0 });
    this.areas = [...this.areas, area];
    return of(area);
  }

  updateArea(areaId: string, name: string) {
    this.updateAreaCalls.push([areaId, name]);
    return of(makeArea({ id: areaId, name }));
  }

  removeArea(areaId: string) {
    this.removeAreaCalls.push(areaId);
    const area = this.areas.find((a) => a.id === areaId);
    if (area && area.collectionCount > 0) {
      return throwError(
        () =>
          new HttpErrorResponse({
            status: 409,
            error: { message: 'Collection area still has collections assigned to it' },
          }),
      );
    }
    return of(undefined);
  }

  moveCollectionToArea(collectionId: string, areaId: string) {
    this.moveCollectionToAreaCalls.push([collectionId, areaId]);
    const area = this.areas.find((a) => a.id === areaId);
    return of(makeCollection({ id: collectionId, areaId, areaName: area?.name ?? '' }));
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
    expect(el.textContent).toContain('Missing');
  });

  it('shows configured object mapping columns for a document', async () => {
    const el = await setup(undefined, [
      makeDocument({
        objectMapping: {
          inventoryNumberColumn: 'Inventory No',
          displayTitleColumn: 'Name',
          displayTitleColumns: ['Name', 'Description'],
          objectNameColumn: null,
          descriptionColumns: ['Description'],
        },
      }),
    ]);
    await expand(el);

    expect(el.textContent).toContain('Configured');
    expect(el.textContent).toContain('Inventory No / Name + Description');
  });

  it('shows the error message for a failed document', async () => {
    const el = await setup(undefined, [
      makeDocument({ status: 'ERROR', errorMessage: 'Too many rows', rowCount: null }),
    ]);
    await expand(el);
    expect(el.querySelector('.badge--error')).not.toBeNull();
    expect(el.querySelector('.documents__error')?.textContent).toContain('Too many rows');
  });

  it('previews columns and uploads only after required mapping is selected', async () => {
    const el = await setup();
    await expand(el);
    const file = new File(['x'], 'new.xlsx');
    const input = el.querySelector<HTMLInputElement>('.upload input[type="file"]')!;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.previewDocumentColumnsCalls).toEqual([['col-zoo', file]]);
    expect(service.uploadCalls).toEqual([]);
    const dialog = el.querySelector<HTMLElement>('[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.textContent).toContain('Configure columns for new.xlsx');

    const selects = dialog.querySelectorAll<HTMLSelectElement>('.mapping-field select');
    selects[0].value = 'Inventory No';
    selects[0].dispatchEvent(new Event('change'));
    const title = Array.from(dialog.querySelectorAll<HTMLInputElement>('.mapping-combo__option input'))
      .find((input) => input.nextElementSibling?.textContent?.trim() === 'Name')!;
    title.checked = true;
    title.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    Array.from(dialog.querySelectorAll<HTMLButtonElement>('.admin-btn'))
      .find((button) => button.textContent?.includes('Upload and index'))!
      .click();
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

  it('configures object snapshot columns for a document', async () => {
    const el = await setup();
    await expand(el);

    Array.from(el.querySelectorAll<HTMLButtonElement>('.doc-btn'))
      .find((b) => b.textContent?.includes('Configure columns'))!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.listDocumentColumnsCalls).toEqual(['doc-1']);

    const selects = el.querySelectorAll<HTMLSelectElement>('.mapping-field select');
    selects[0].value = 'Inventory No';
    selects[0].dispatchEvent(new Event('change'));
    const title = Array.from(el.querySelectorAll<HTMLInputElement>('.mapping-combo__option input'))
      .find((input) => input.nextElementSibling?.textContent?.trim() === 'Name')!;
    title.checked = true;
    title.dispatchEvent(new Event('change'));
    selects[1].value = 'Name';
    selects[1].dispatchEvent(new Event('change'));
    const description = Array.from(
      el.querySelectorAll<HTMLInputElement>('.mapping-descriptions input'),
    ).find((input) => input.nextElementSibling?.textContent?.trim() === 'Description')!;
    description.checked = true;
    description.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('.mapping-panel__actions .admin-btn'))
      .find((button) => button.textContent?.includes('Save mapping'))!
      .click();
    await fixture.whenStable();

    expect(service.updateObjectMappingCalls).toEqual([
      [
        'doc-1',
        {
          inventoryNumberColumn: 'Inventory No',
          displayTitleColumns: ['Name'],
          objectNameColumn: 'Name',
          descriptionColumns: ['Description'],
        },
      ],
    ]);
  });

  describe('SYS_ADMIN catalog administration', () => {
    it('hides admin controls for non-SYS_ADMIN staff', async () => {
      const el = await setup(undefined, undefined, 'CURATORIAL');
      expect(el.querySelector('.new-collection')).toBeNull();
      expect(el.querySelector('.collection__admin-actions')).toBeNull();
      expect(el.querySelector('.area-admin')).toBeNull();
    });

    it('groups collections under their area', async () => {
      const el = await setup([
        makeCollection({ id: 'col-zoo', name: 'Zoology', areaName: 'Natural History' }),
        makeCollection({
          id: 'col-arch',
          name: 'Archaeology',
          areaId: 'area-human',
          areaName: 'Human Sciences',
        }),
      ]);
      const titles = Array.from(el.querySelectorAll('.area-group__title')).map((t) =>
        t.textContent?.trim(),
      );
      expect(titles.some((t) => t?.startsWith('Human Sciences'))).toBe(true);
      expect(titles.some((t) => t?.startsWith('Natural History'))).toBe(true);
    });

    it('requires both a name and an area before creating a collection', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      const input = el.querySelector<HTMLInputElement>('.new-collection__input')!;
      input.value = 'Mineralogy';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      const submit = el.querySelector<HTMLButtonElement>('.new-collection__submit')!;
      expect(submit.disabled).toBe(true);

      const select = el.querySelector<HTMLSelectElement>('.new-collection__area')!;
      select.value = 'area-nat-hist';
      select.dispatchEvent(new Event('change'));
      fixture.detectChanges();
      expect(submit.disabled).toBe(false);

      submit.click();
      await fixture.whenStable();
      expect(service.createCollectionCalls).toEqual([['Mineralogy', 'area-nat-hist']]);
    });

    it('renames a collection inline', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      Array.from(el.querySelectorAll<HTMLButtonElement>('.collection__admin-actions .admin-btn'))
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
      Array.from(el.querySelectorAll<HTMLButtonElement>('.collection__admin-actions .admin-btn'))
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
      Array.from(el.querySelectorAll<HTMLButtonElement>('.collection__admin-actions .admin-btn'))
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

    it('creates a collection area', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      const input = el.querySelector<HTMLInputElement>('.area-admin__input')!;
      input.value = 'Media';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      Array.from(el.querySelectorAll<HTMLButtonElement>('.area-admin button'))
        .find((b) => b.textContent?.includes('Create area'))!
        .click();
      await fixture.whenStable();

      expect(service.createAreaCalls).toEqual(['Media']);
    });

    it('renames a collection area inline', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      Array.from(el.querySelectorAll<HTMLButtonElement>('.area-admin__item .admin-btn'))
        .find((b) => b.textContent?.includes('Rename'))!
        .click();
      fixture.detectChanges();

      const input = el.querySelector<HTMLInputElement>('.area-admin__item .area-admin__input')!;
      input.value = 'Natural Sciences';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      Array.from(el.querySelectorAll<HTMLButtonElement>('.area-admin__item .admin-btn'))
        .find((b) => b.textContent?.includes('Save'))!
        .click();
      await fixture.whenStable();

      expect(service.updateAreaCalls).toEqual([['area-nat-hist', 'Natural Sciences']]);
    });

    it('asks for confirmation before removing an area, surfacing an in-use conflict', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

      Array.from(el.querySelectorAll<HTMLButtonElement>('.area-admin__item'))[0]
        .querySelector<HTMLButtonElement>('.admin-btn.admin-btn--danger')!
        .click();
      await fixture.whenStable();
      fixture.detectChanges();

      expect(confirmSpy).toHaveBeenCalled();
      expect(service.removeAreaCalls).toEqual(['area-nat-hist']);
      expect(el.textContent).toContain('Action not allowed');
    });

    it('moves a collection to a different area', async () => {
      const el = await setup(undefined, undefined, 'SYS_ADMIN');
      await expand(el);

      const select = el.querySelector<HTMLSelectElement>('.move-area__select')!;
      select.value = 'area-media';
      select.dispatchEvent(new Event('change'));
      fixture.detectChanges();
      Array.from(el.querySelectorAll<HTMLButtonElement>('.move-area .admin-btn'))
        .find((b) => b.textContent?.includes('Move'))!
        .click();
      await fixture.whenStable();

      expect(service.moveCollectionToAreaCalls).toEqual([['col-zoo', 'area-media']]);
    });
  });
});
