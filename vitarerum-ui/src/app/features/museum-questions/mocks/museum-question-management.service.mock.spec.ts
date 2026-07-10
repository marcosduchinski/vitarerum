import { firstValueFrom } from 'rxjs';

import { MuseumQuestionManagementServiceMock } from './museum-question-management.service.mock';

describe('MuseumQuestionManagementServiceMock', () => {
  let service: MuseumQuestionManagementServiceMock;

  beforeEach(async () => {
    service = new MuseumQuestionManagementServiceMock();
    await firstValueFrom(service.runTriage('q-1'));
  });

  it('normalizes submitted search terms like the real API: trims, drops blanks, dedupes, and fills a missing language', async () => {
    const result = await firstValueFrom(
      service.syncTriageSearchTerms('q-1', [
        { english: '  Fox  ', portuguese: '  Raposa  ' },
        { english: '', portuguese: '' },
        { english: '   ', portuguese: '   ' },
        { english: 'FOX', portuguese: 'RAPOSA' },
        { english: '', portuguese: 'Only Portuguese' },
      ]),
    );

    expect(result.mentionedObjects).toEqual([
      { english: 'Fox', portuguese: 'Raposa', origin: 'STAFF' },
      { english: 'Only Portuguese', portuguese: 'Only Portuguese', origin: 'STAFF' },
    ]);
  });

  it('rejects more than the staff search-term limit only after normalizing', async () => {
    // 11 blank rows normalize down to 0 terms — must not be rejected as "too many".
    const blankRows = Array.from({ length: 11 }, () => ({ english: '', portuguese: '' }));
    const result = await firstValueFrom(service.syncTriageSearchTerms('q-1', blankRows));
    expect(result.mentionedObjects).toEqual([]);
  });
});
