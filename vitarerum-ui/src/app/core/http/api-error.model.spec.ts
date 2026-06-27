import { HttpErrorResponse } from '@angular/common/http';

import {
  ApiError,
  getApiErrorPresentation,
  toApiError,
} from './api-error.model';

function makeHttpError(status: number, body?: unknown): HttpErrorResponse {
  return new HttpErrorResponse({ status, error: body, url: 'https://api.example.test' });
}

describe('toApiError', () => {
  it('maps 403 to forbidden', () => {
    const result = toApiError(makeHttpError(403));
    expect(result.kind).toBe('forbidden');
    expect(result.status).toBe(403);
  });

  it('maps 404 to not-found', () => {
    expect(toApiError(makeHttpError(404)).kind).toBe('not-found');
  });

  it('maps 409 to conflict', () => {
    expect(toApiError(makeHttpError(409)).kind).toBe('conflict');
  });

  it('maps 422 to validation and extracts field errors from errors array', () => {
    const body = {
      error: 'VALIDATION_FAILED',
      message: 'Validation failed',
      errors: [
        { field: 'title', message: 'must not be blank' },
        { field: 'beginDate', message: 'must be a future date' },
      ],
    };
    const result = toApiError(makeHttpError(422, body));
    expect(result.kind).toBe('validation');
    expect(result.serverMessage).toBe('Validation failed');
    expect(result.fieldErrors).toHaveLength(2);
    expect(result.fieldErrors[0]).toEqual({ field: 'title', message: 'must not be blank' });
  });

  it('maps 422 and extracts field errors from fieldErrors map', () => {
    const body = { fieldErrors: { title: 'must not be blank' } };
    const result = toApiError(makeHttpError(422, body));
    expect(result.kind).toBe('validation');
    expect(result.fieldErrors[0]).toEqual({ field: 'title', message: 'must not be blank' });
  });

  it('maps 500 to server-error', () => {
    expect(toApiError(makeHttpError(500)).kind).toBe('server-error');
  });

  it('maps 503 to server-error', () => {
    expect(toApiError(makeHttpError(503)).kind).toBe('server-error');
  });

  it('maps status 0 to network-error', () => {
    expect(toApiError(makeHttpError(0)).kind).toBe('network-error');
  });

  it('maps non-HttpErrorResponse to unknown', () => {
    const result = toApiError(new Error('oops'));
    expect(result.kind).toBe('unknown');
    expect(result.status).toBe(0);
    expect(result.fieldErrors).toHaveLength(0);
  });

  it('extracts serverMessage from body', () => {
    const result = toApiError(makeHttpError(409, { message: 'Already assigned' }));
    expect(result.serverMessage).toBe('Already assigned');
  });

  it('returns empty fieldErrors for non-validation errors', () => {
    expect(toApiError(makeHttpError(500)).fieldErrors).toHaveLength(0);
  });
});

describe('getApiErrorPresentation', () => {
  function make(kind: ApiError['kind'], serverMessage: string | null = null): ApiError {
    return { kind, status: 0, serverMessage, fieldErrors: [] };
  }

  it('forbidden: warning tone, not retryable', () => {
    const p = getApiErrorPresentation(make('forbidden'));
    expect(p.tone).toBe('warning');
    expect(p.retryable).toBe(false);
    expect(p.title).toBe('Access denied');
  });

  it('not-found: info tone, not retryable', () => {
    const p = getApiErrorPresentation(make('not-found'));
    expect(p.tone).toBe('info');
    expect(p.retryable).toBe(false);
  });

  it('conflict: uses serverMessage when present', () => {
    const p = getApiErrorPresentation(make('conflict', 'Proposal already assigned'));
    expect(p.message).toBe('Proposal already assigned');
  });

  it('conflict: falls back to default when serverMessage is null', () => {
    const p = getApiErrorPresentation(make('conflict', null));
    expect(p.message).toContain('conflicts with');
  });

  it('validation: warning tone, not retryable', () => {
    const p = getApiErrorPresentation(make('validation'));
    expect(p.tone).toBe('warning');
    expect(p.retryable).toBe(false);
  });

  it('server-error: danger tone, retryable', () => {
    const p = getApiErrorPresentation(make('server-error'));
    expect(p.tone).toBe('danger');
    expect(p.retryable).toBe(true);
  });

  it('network-error: danger tone, retryable', () => {
    const p = getApiErrorPresentation(make('network-error'));
    expect(p.tone).toBe('danger');
    expect(p.retryable).toBe(true);
  });

  it('unknown: danger tone, retryable', () => {
    const p = getApiErrorPresentation(make('unknown'));
    expect(p.tone).toBe('danger');
    expect(p.retryable).toBe(true);
  });
});
