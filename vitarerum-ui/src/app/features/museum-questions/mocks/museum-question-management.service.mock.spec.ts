import { firstValueFrom } from 'rxjs';

import { MuseumQuestionManagementServiceMock } from './museum-question-management.service.mock';

describe('MuseumQuestionManagementServiceMock', () => {
  let service: MuseumQuestionManagementServiceMock;

  beforeEach(() => {
    service = new MuseumQuestionManagementServiceMock();
  });

  it('lists submitted questions by default filters', async () => {
    const page = await firstValueFrom(service.list({ status: 'SUBMITTED', page: 0, size: 20 }));

    expect(page.content.map((question) => question.id)).toEqual(['q-1']);
  });

  it('answers a submitted question', async () => {
    const updated = await firstValueFrom(
      service.answer('q-1', { answerBody: '<p>Manual answer</p>' }),
    );

    expect(updated.status).toBe('ANSWERED');
    expect(updated.answerBody).toBe('<p>Manual answer</p>');
  });

  it('marks a submitted question out of scope', async () => {
    const updated = await firstValueFrom(
      service.markOutOfScope('q-1', { reason: 'Exhibition question' }),
    );

    expect(updated.status).toBe('OUT_OF_SCOPE');
    expect(updated.outOfScopeReason).toBe('Exhibition question');
  });
});
