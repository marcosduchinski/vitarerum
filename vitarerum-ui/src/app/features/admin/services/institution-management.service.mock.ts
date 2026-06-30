import { Injectable } from '@angular/core';
import {
  Institution,
  InstitutionPayload,
} from '@core/auth/models/institution.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { Observable, of, throwError } from 'rxjs';

import {
  makePageFrom,
  MOCK_GROUPS,
  MOCK_INSTITUTIONS,
} from '../../collections/proposals/mocks/mock-data';

@Injectable()
export class InstitutionManagementServiceMock {
  private readonly institutions: Institution[] = structuredClone(MOCK_INSTITUTIONS);

  listInstitutions(query: PageQuery = {}): Observable<Page<Institution>> {
    const sorted = [...this.institutions].sort((a, b) => a.name.localeCompare(b.name));
    return of(makePageFrom(sorted, query));
  }

  getInstitution(institutionId: string): Observable<Institution> {
    const institution = this.institutions.find(i => i.id === institutionId);
    if (!institution) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of(institution);
  }

  createInstitution(payload: InstitutionPayload): Observable<Institution> {
    if (this.nameTaken(payload.name)) {
      return throwError(() => this.conflict('INSTITUTION_NAME_ALREADY_EXISTS'));
    }
    const institution: Institution = { id: `inst-${Date.now()}`, ...payload };
    this.institutions.push(institution);
    return of(institution);
  }

  updateInstitution(
    institutionId: string,
    payload: InstitutionPayload,
  ): Observable<Institution> {
    const idx = this.institutions.findIndex(i => i.id === institutionId);
    if (idx === -1) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (this.nameTaken(payload.name, institutionId)) {
      return throwError(() => this.conflict('INSTITUTION_NAME_ALREADY_EXISTS'));
    }
    const updated: Institution = { id: institutionId, ...payload };
    this.institutions[idx] = updated;
    return of(updated);
  }

  deleteInstitution(institutionId: string): Observable<void> {
    const idx = this.institutions.findIndex(i => i.id === institutionId);
    if (idx === -1) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    if (MOCK_GROUPS.some(g => g.institutionId === institutionId)) {
      return throwError(() => this.conflict('INSTITUTION_IN_USE'));
    }
    this.institutions.splice(idx, 1);
    return of(undefined);
  }

  private nameTaken(name: string, exceptId?: string): boolean {
    const key = name.trim().toLowerCase();
    return this.institutions.some(
      i => i.id !== exceptId && i.name.trim().toLowerCase() === key,
    );
  }

  private conflict(error: string): { status: number; error: { error: string } } {
    return { status: 409, error: { error } };
  }
}
