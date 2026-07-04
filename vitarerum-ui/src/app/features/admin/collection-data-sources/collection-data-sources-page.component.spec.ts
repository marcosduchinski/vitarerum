import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { CollectionDataSource, SourceDocument } from '../models/collection-data-source.model';
import { COLLECTION_DATA_SOURCE_SERVICE } from '../services/collection-data-source.service';
import { CollectionDataSourcesPageComponent } from './collection-data-sources-page.component';

function makeCollection(overrides: Partial<CollectionDataSource> = {}): CollectionDataSource {
  return {
    id: 'col-zoo',
    name: 'Zoology',
    active: true,
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

class ServiceStub {
  collections: CollectionDataSource[] = [makeCollection()];
  documents: SourceDocument[] = [makeDocument()];
  readonly uploadCalls: [string, File][] = [];
  readonly removeCalls: string[] = [];
  readonly reindexCalls: string[] = [];

  listCollections() {
    return of(this.collections);
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

  assignCurator() {
    return of(null);
  }

  removeCurator() {
    return of(undefined);
  }
}

describe('CollectionDataSourcesPageComponent', () => {
  let fixture: ComponentFixture<CollectionDataSourcesPageComponent>;
  let service: ServiceStub;

  async function setup(
    collections?: CollectionDataSource[],
    documents?: SourceDocument[],
  ): Promise<HTMLElement> {
    service = new ServiceStub();
    if (collections) service.collections = collections;
    if (documents) service.documents = documents;
    await TestBed.configureTestingModule({
      imports: [CollectionDataSourcesPageComponent],
      providers: [{ provide: COLLECTION_DATA_SOURCE_SERVICE, useValue: service }],
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
});
