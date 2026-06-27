import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PROJECT_API_SERVICE } from '../services/project-api.service';

/**
 * Gate for the publication log page. The publication log is readable (and, for
 * the external requester, writable) while the project is IN_PROGRESS, and stays
 * readable once COMPLETED — so researchers may reach it in both phases (unlike
 * the object access/occurrence logs, which lock to IN_PROGRESS). Researchers are
 * bounced back to the project detail for CREATED/CANCELLED projects. Staff (any
 * non-EXTERNAL group) always pass; the backend enforces its own write guards.
 */
export const projectPublicationAccessGuard: CanActivateFn = async (route) => {
  const identity = inject(IDENTITY_SERVICE);
  const projectService = inject(PROJECT_API_SERVICE);
  const router = inject(Router);

  const group = identity.session()?.group;
  if (!group) return router.createUrlTree(['/p/dashboard']);
  if (group !== 'EXTERNAL') return true;

  const projectId = route.paramMap.get('id');
  if (!projectId) return router.createUrlTree(['/p/collections/projects/my']);

  try {
    const project = await firstValueFrom(projectService.getProject(projectId));
    if (project.status === 'IN_PROGRESS' || project.status === 'COMPLETED') return true;
    return router.createUrlTree(['/p/collections/projects', projectId], {
      queryParams: { returnTo: '/p/collections/projects/my', returnLabel: 'my projects' },
    });
  } catch {
    return router.createUrlTree(['/p/collections/projects/my']);
  }
};
