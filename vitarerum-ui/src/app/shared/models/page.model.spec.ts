import { ApiErrorResponse, Page } from './page.model';

describe('shared API envelopes', () => {
  it('models paginated endpoint responses', () => {
    const page: Page<{ readonly id: string }> = {
      content: [{ id: 'proposal-1' }],
      page: 0,
      size: 20,
      totalElements: 1,
      totalPages: 1,
    };

    expect(page.content[0]?.id).toBe('proposal-1');
    expect(page.totalPages).toBe(1);
  });

  it('models machine-readable API errors', () => {
    const error: ApiErrorResponse = {
      error: 'INVALID_TRANSITION',
      message: 'Proposal must be PENDING to be approved',
    };

    expect(error.error).toBe('INVALID_TRANSITION');
    expect(error.message).toContain('PENDING');
  });
});
