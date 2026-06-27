import { IdentityUser } from './identity-user.model';
import { SessionPermission } from './identity-session.model';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  accessToken: string;
  user: IdentityUser;
  permissions: readonly SessionPermission[];
}
