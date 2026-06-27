import { HttpErrorResponse } from '@angular/common/http';

import { ErrorMessageTone } from '@shared/components/error-message/error-message.component';

export type ApiErrorKind =
  | 'forbidden'
  | 'not-found'
  | 'conflict'
  | 'validation'
  | 'server-error'
  | 'network-error'
  | 'unknown';

export interface ValidationFieldError {
  readonly field: string;
  readonly message: string;
}

export interface ApiError {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly serverMessage: string | null;
  readonly fieldErrors: readonly ValidationFieldError[];
}

export interface ApiErrorPresentation {
  readonly title: string;
  readonly message: string;
  readonly tone: ErrorMessageTone;
  readonly retryable: boolean;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof HttpErrorResponse) {
    const kind = statusToKind(error.status);
    const body = error.error as Record<string, unknown> | null | undefined;
    const serverMessage = typeof body?.['message'] === 'string' ? body['message'] : null;
    return {
      kind,
      status: error.status,
      serverMessage,
      fieldErrors: extractFieldErrors(body),
    };
  }
  return { kind: 'unknown', status: 0, serverMessage: null, fieldErrors: [] };
}

export function getApiErrorPresentation(error: ApiError): ApiErrorPresentation {
  switch (error.kind) {
    case 'forbidden':
      return {
        title: 'Access denied',
        message: 'You do not have permission to perform this action.',
        tone: 'warning',
        retryable: false,
      };
    case 'not-found':
      return {
        title: 'Not found',
        message: 'The requested resource no longer exists.',
        tone: 'info',
        retryable: false,
      };
    case 'conflict':
      return {
        title: 'Action not allowed',
        message: error.serverMessage ?? 'This action conflicts with the current state.',
        tone: 'warning',
        retryable: false,
      };
    case 'validation':
      return {
        title: 'Invalid data',
        message: error.serverMessage ?? 'Please review the fields below.',
        tone: 'warning',
        retryable: false,
      };
    case 'server-error':
      return {
        title: 'Server error',
        message: 'An unexpected error occurred. Try again in a moment.',
        tone: 'danger',
        retryable: true,
      };
    case 'network-error':
      return {
        title: 'Connection error',
        message: 'Could not reach the server. Check your connection.',
        tone: 'danger',
        retryable: true,
      };
    default:
      return {
        title: 'Unexpected error',
        message: 'Something went wrong. Try again or contact support.',
        tone: 'danger',
        retryable: true,
      };
  }
}

function statusToKind(status: number): ApiErrorKind {
  if (status === 0) return 'network-error';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not-found';
  if (status === 409) return 'conflict';
  if (status === 422) return 'validation';
  if (status >= 500) return 'server-error';
  return 'unknown';
}

function extractFieldErrors(body: Record<string, unknown> | null | undefined): readonly ValidationFieldError[] {
  if (!body) return [];

  // Format: { errors: [{ field, message }] }
  if (Array.isArray(body['errors'])) {
    return (body['errors'] as unknown[])
      .filter((e): e is { field: string; message: string } =>
        typeof (e as Record<string, unknown>)['field'] === 'string' &&
        typeof (e as Record<string, unknown>)['message'] === 'string',
      )
      .map(e => ({ field: e.field, message: e.message }));
  }

  // Format: { fieldErrors: { fieldName: message } }
  if (body['fieldErrors'] && typeof body['fieldErrors'] === 'object') {
    return Object.entries(body['fieldErrors'] as Record<string, unknown>)
      .filter(([, v]) => typeof v === 'string')
      .map(([field, message]) => ({ field, message: message as string }));
  }

  return [];
}
