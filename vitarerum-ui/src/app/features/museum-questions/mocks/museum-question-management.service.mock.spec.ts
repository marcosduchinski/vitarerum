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
    expect(page.content[0].attachmentCount).toBe(1);
    expect('attachments' in page.content[0]).toBe(false);
    expect(page.content[0].assignedTo).toBeNull();
  });

  it('keeps attachment metadata on the detail response', async () => {
    const question = await firstValueFrom(service.get('q-1'));

    expect(question.attachments.map((attachment) => attachment.fileName)).toEqual([
      'collection-label.png',
    ]);
  });

  it('answers a submitted question', async () => {
    const updated = await firstValueFrom(
      service.answer('q-1', { answerBody: '<p>Manual answer</p>' }),
    );

    expect(updated.status).toBe('ANSWERED');
    expect(updated.answerBody).toBe('<p>Manual answer</p>');
  });

  it('forwards a submitted question to my enquiries', async () => {
    const updated = await firstValueFrom(
      service.forward('q-1', { targetPermissionId: 'perm-carol' }),
    );
    const page = await firstValueFrom(
      service.list({ assignedTo: 'perm-carol', status: 'IN_PROGRESS', page: 0, size: 20 }),
    );

    expect(updated.assignedTo?.permissionId).toBe('perm-carol');
    expect(updated.status).toBe('IN_PROGRESS');
    expect(page.content.map((question) => question.id)).toContain('q-1');
  });

  it('removes forwarded questions from new inquiries', async () => {
    await firstValueFrom(service.forward('q-1', { targetPermissionId: 'perm-carol' }));
    const page = await firstValueFrom(
      service.list({ status: 'SUBMITTED', unassignedOnly: true, page: 0, size: 20 }),
    );

    expect(page.content.map((question) => question.id)).not.toContain('q-1');
  });

  it('marks a submitted question out of scope', async () => {
    const updated = await firstValueFrom(
      service.markOutOfScope('q-1', { reason: 'Exhibition question' }),
    );

    expect(updated.status).toBe('OUT_OF_SCOPE');
    expect(updated.outOfScopeReason).toBe('Exhibition question');
  });
});
