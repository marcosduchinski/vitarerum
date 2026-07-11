import { ObjectSearchHit } from '@features/objects/models/object-search.model';

import { adaptSearchHitToRequestedObject } from './requested-object-search.adapter';

const HIT: ObjectSearchHit = {
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
    objectName: 'Panthera onca',
    briefDescriptionSnapshot: 'Large cat.',
    category: 'Zoology',
  },
};

describe('adaptSearchHitToRequestedObject', () => {
  it('converts a search hit snapshot into an add-requested-object item', () => {
    const result = adaptSearchHitToRequestedObject(HIT);

    expect(result).toEqual({
      ok: true,
      item: {
        inventoryNumber: 'ZOO-001',
        displayTitle: 'Jaguar',
        objectName: 'Panthera onca',
        briefDescriptionSnapshot: 'Large cat.',
        category: 'Zoology',
        description: 'Zoology / zoo.xlsx / Objects row 2',
      },
    });
  });

  it('rejects rows without an object snapshot', () => {
    const result = adaptSearchHitToRequestedObject({ ...HIT, objectSnapshot: null });

    expect(result).toEqual({
      ok: false,
      reason: 'Cannot add this row: missing inventory/title/name mapping.',
    });
  });
});
