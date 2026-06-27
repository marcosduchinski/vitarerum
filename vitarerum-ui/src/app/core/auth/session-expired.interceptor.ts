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
      // session — let the login page surface it instead of redirecting.
      const isLoginRequest = request.url.includes('/auth/login');
      if (error instanceof HttpErrorResponse && error.status === 401 && !isLoginRequest) {
        identity.signOut();
        router.navigateByUrl('/login').catch(console.error);
      }

      return throwError(() => error);
    }),
  );
};
