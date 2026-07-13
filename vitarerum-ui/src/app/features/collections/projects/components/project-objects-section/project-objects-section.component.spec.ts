import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ObjectSearchResult } from '@features/objects/models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '@features/objects/services/object-search.service';

import { AddProjectObjectsRequest, CollectionUseProjectObject } from '../../models/project.model';
import { ProjectObjectsSectionComponent } from './project-objects-section.component';

const PROJECT_OBJECT: CollectionUseProjectObject = {
  id: 'project-object-1',
  inventoryNumber: 'INV-001',
  displayTitle: 'Book of Hours',
  objectName: 'Illuminated manuscript',
  briefDescriptionSnapshot: 'Decorated manuscript snapshot.',
  category: 'manuscript',
  description: 'Selected from object index.',
};

describe('ProjectObjectsSectionComponent', () => {
  let fixture: ComponentFixture<ProjectObjectsSectionComponent>;
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

  async function setup(
    objects: CollectionUseProjectObject[] = [PROJECT_OBJECT],
    canManage = true,
  ): Promise<HTMLElement> {
    objectSearch = new ObjectSearchServiceStub();
    await TestBed.configureTestingModule({
      imports: [ProjectObjectsSectionComponent],
      providers: [{ provide: OBJECT_SEARCH_SERVICE, useValue: objectSearch }],
    }).compileComponents();

    fixture = TestBed.createComponent(ProjectObjectsSectionComponent);
    fixture.componentRef.setInput('objects', objects);
    fixture.componentRef.setInput('canManage', canManage);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  function addObjectButton(el: HTMLElement): HTMLButtonElement {
    return Array.from(el.querySelectorAll<HTMLButtonElement>('.objects-action')).find(
      (button) => button.textContent?.includes('Add object'),
    )!;
  }

  it('lists the project objects', async () => {
    const el = await setup();

    expect(el.textContent).toContain('Objects');
    expect(el.textContent).toContain('INV-001');
    expect(el.textContent).toContain('Book of Hours');
  });

  it('shows an empty state', async () => {
    const el = await setup([]);

    expect(el.textContent).toContain('No objects linked to this project.');
  });

  it('hides add/remove actions when the caller cannot manage the project', async () => {
    const el = await setup([PROJECT_OBJECT], false);

    expect(addObjectButton(el)).toBeUndefined();
    expect(el.querySelector('.object-row__remove')).toBeNull();
  });

  it('confirms before emitting remove requests', async () => {
    const el = await setup();
    const emitted: string[] = [];
    fixture.componentRef.instance.removeRequested.subscribe((id) => emitted.push(id));

    el.querySelector<HTMLButtonElement>('.object-row__remove')!.click();
    fixture.detectChanges();

    expect(emitted).toEqual([]);
    expect(el.textContent).toContain('Remove object?');
    expect(el.textContent).toContain('Remove Book of Hours from this project.');

    const confirmButton = Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Remove object',
    );
    expect(confirmButton).toBeDefined();
    confirmButton!.click();

    expect(emitted).toEqual(['project-object-1']);
  });

  it('searches and emits selected object snapshots from the add modal', async () => {
    const el = await setup();
    const emitted: AddProjectObjectsRequest[] = [];
    fixture.componentRef.instance.addRequested.subscribe((payload) => emitted.push(payload));

    addObjectButton(el).click();
    fixture.detectChanges();

    expect(el.querySelector('.add-modal')).not.toBeNull();
    expect(el.textContent).toContain('Add object');

    const input = el.querySelector<HTMLInputElement>('.object-search__input')!;
    input.value = 'jaguar';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    el.querySelector<HTMLButtonElement>('.object-search button[type="submit"]')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Jaguar');
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
