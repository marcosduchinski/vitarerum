import { PermissionSummary } from './permission.model';

export interface User {
  readonly id: string;
  readonly name: string;
  readonly email: string;
}

export interface UserDetail extends User {
  readonly permissions: readonly PermissionSummary[];
}
