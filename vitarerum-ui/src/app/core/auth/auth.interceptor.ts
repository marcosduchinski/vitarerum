import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { IDENTITY_SERVICE } from './identity.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const identity = inject(IDENTITY_SERVICE);
  const token = identity.getAccessToken();
  const permissionId = identity.getPermissionId();

  if (token === null && permissionId === null) {
    return next(request);
  }

  const setHeaders: Record<string, string> = {};
  if (token !== null) {
    setHeaders['Authorization'] = `Bearer ${token}`;
  }
  if (permissionId !== null) {
    setHeaders['X-Permission-Id'] = permissionId;
  }

  return next(request.clone({ setHeaders }));
};
