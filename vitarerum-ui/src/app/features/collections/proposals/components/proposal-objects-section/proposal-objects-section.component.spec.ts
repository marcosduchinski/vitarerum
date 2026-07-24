import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ObjectSearchResult } from '@features/objects/models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '@features/objects/services/object-search.service';
import { AddRequestedObjectsRequest } from '../../models/proposal-actions.model';
import { RequestedObject } from '../../models/proposal.model';
import { ProposalObjectsSectionComponent } from './proposal-objects-section.component';

const REQUESTED_OBJECT: RequestedObject = {
  id: 'requested-object-1',
  objectReference: {
    inventoryNumber: 'INV-001',
    displayTitle: 'Book of Hours',
    objectName: 'Illuminated manuscript',
    briefDescriptionSnapshot: 'Decorated manuscript snapshot.',
  },
  category: 'manuscript',
  description: 'Requested for comparative study.',
  requestedAt: '2026-06-01T10:00:00Z',
  requestedBy: {
    permissionId: 'permission-1',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
};

describe('ProposalObjectsSectionComponent', () => {
  let fixture: ComponentFixture<ProposalObjectsSectionComponent>;
  let objectSearch: ObjectSearchServiceStub;

  class ObjectSearchServiceStub {
    result: ObjectSearchResult = {
      total: 2,
      page: 0,
      size: 20,
      items: [
        {
          collectionId: 'col-zoo',
          collectionName: 'Zoology',
          sourceDocumentId: 'doc-1',
          fileName: 'zoo.xlsx',
          sheet: 'Objects',
          rowNumber: 2,
          cells: { 'Inventory No': 'ZOO-001', Name: 'Jaguar' },
          highlight: '<b>Jaguar</b>',
          objectSnapshot: {
            inventoryNumber: 'ZOO-001',
            displayTitle: 'Jaguar',
            objectName: 'Jaguar',
            briefDescriptionSnapshot: 'Large cat.',
            category: 'Zoology',
          },
          matchReasons: [{ method: 'exact', label: 'Exact', columns: ['Name'] }],
        },
        {
          collectionId: 'col-arc',
          collectionName: 'Archaeology',
          sourceDocumentId: 'doc-2',
          fileName: 'arc.xlsx',
          sheet: 'Finds',
          rowNumber: 3,
          cells: { Code: 'ARC-001' },
          highlight: '<b>ARC-001</b>',
          objectSnapshot: null,
          matchReasons: [{ method: 'approximate', label: 'Approximate', columns: [] }],
        },
      ],
    };

    search() {
      return of(this.result);
    }

    listSearchableCollections() {
      return of([]);
    }
  }

  async function setup(objects: RequestedObject[] = [REQUESTED_OBJECT]): Promise<HTMLElement> {
    objectSearch = new ObjectSearchServiceStub();
    await TestBed.configureTestingModule({
      imports: [ProposalObjectsSectionComponent],
      providers: [{ provide: OBJECT_SEARCH_SERVICE, useValue: objectSearch }],
    }).compileComponents();

    fixture = TestBed.createComponent(ProposalObjectsSectionComponent);
    fixture.componentRef.setInput('objects', objects);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('lists requested objects', async () => {
    const el = await setup();

    expect(el.textContent).toContain('Requested objects');
    expect(el.textContent).toContain('INV-001');
    expect(el.textContent).toContain('Book of Hours');
    expect(el.textContent).toContain('Illuminated manuscript');
  });

  it('shows an empty state', async () => {
    const el = await setup([]);

    expect(el.textContent).toContain('No objects have been requested');
  });

  it('confirms before emitting remove requests', async () => {
    const el = await setup();
    const emitted: string[] = [];
    fixture.componentRef.instance.removeRequested.subscribe((id) => emitted.push(id));

    el.querySelector<HTMLButtonElement>('.object__remove')!.click();
    fixture.detectChanges();

    expect(emitted).toEqual([]);
    expect(el.textContent).toContain('Remove requested object?');
    expect(el.textContent).toContain('This will remove Book of Hours from this proposal.');

    const confirmButton = Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Remove object',
    );
    expect(confirmButton).toBeDefined();
    confirmButton!.click();

    expect(emitted).toEqual(['requested-object-1']);
  });

  it('searches and emits selected object snapshots from the add modal', async () => {
    const el = await setup();
    const emitted: AddRequestedObjectsRequest[] = [];
    fixture.componentRef.instance.addRequested.subscribe((payload) => emitted.push(payload));

    el.querySelector<HTMLButtonElement>('.objects__add')!.click();
    fixture.detectChanges();

    expect(el.querySelector('.add-modal')).not.toBeNull();
    expect(el.textContent).toContain('Add requested object');

    const input = el.querySelector<HTMLInputElement>('.object-search__input')!;
    input.value = 'jaguar';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    el.querySelector<HTMLButtonElement>('.object-search__button')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Jaguar');
    expect(el.querySelector('.search-explainer summary')?.textContent).toContain('How search works');
    expect(el.textContent).toContain('Exact');
    expect(el.textContent).toContain('Text');
    expect(el.textContent).toContain('Approximate');
    expect(el.textContent).toContain(
      'Search runs automatically across the selected searchable columns',
    );
    expect(el.textContent).toContain('Matched by Exact - Name');
    expect(el.textContent).toContain('Matched by Approximate');
    expect(el.textContent).toContain('Zoology');
    expect(el.textContent).toContain('Large cat.');
    expect(el.textContent).toContain('Cannot add this row');

    const checkbox = el.querySelector<HTMLInputElement>('.search-hit input[type="checkbox"]')!;
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('.add-modal__footer button'))
      .find((button) => button.textContent?.includes('Add selected'))!
      .click();

    expect(emitted).toEqual([
      {
        objects: [
          {
            inventoryNumber: 'ZOO-001',
            displayTitle: 'Jaguar',
            objectName: 'Jaguar',
            briefDescriptionSnapshot: 'Large cat.',
            category: 'Zoology',
            description: 'Zoology / zoo.xlsx / Objects row 2',
          },
        ],
      },
    ]);
  });
});
