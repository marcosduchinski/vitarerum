import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { IDENTITY_SERVICE } from './identity.service';

export const sessionExpiredInterceptor: HttpInterceptorFn = (request, next) => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  return next(request).pipe(
    catchError((error: unknown) => {
      // A 401 from the login endpoint means bad credentials, not an expired
      // session — let the login page surface it instead of redirecting. The
      // public password-reset endpoints carry no session to expire either;
      // they're excluded defensively (the backend's own contract is that
      // an invalid/expired/used reset token is a 404, never a 401).
      const isPublicAuthRequest =
        request.url.includes('/auth/login') ||
        request.url.includes('/auth/password-reset/request') ||
        request.url.includes('/auth/password-reset/confirm');
      if (error instanceof HttpErrorResponse && error.status === 401 && !isPublicAuthRequest) {
        identity.signOut();
        router.navigateByUrl('/login').catch(console.error);
      }

      return throwError(() => error);
    }),
  );
};
