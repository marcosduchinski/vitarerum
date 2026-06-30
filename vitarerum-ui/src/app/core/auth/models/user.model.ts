import { PermissionSummary } from './permission.model';

export interface User {
  readonly id: string;
  readonly name: string;
  readonly email: string;
}

export interface UserDetail extends User {
  readonly permissions: readonly PermissionSummary[];
}

export interface CreateUserPayload {
  readonly name: string;
  readonly email: string;
  // Optional per the API, but an account without one cannot log in.
  readonly password?: string;
}
