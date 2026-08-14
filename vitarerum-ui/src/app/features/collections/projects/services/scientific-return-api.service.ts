import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '@core/config/app-config.model';
import { buildHttpParams } from '@core/http/http-params.util';

import {
  CandidateDecisionRecord,
  CandidateDecisionRequest,
  ScientificReturnCandidate,
  ScientificReturnCandidatesPage,
  ScientificReturnCandidateStatus,
  ScientificReturnRun,
  ScientificReturnRunsPage,
  ScientificReturnWatch,
  ScientificReturnWatchStatus,
} from '../models/scientific-return.model';

@Injectable({ providedIn: 'root' })
export class ScientificReturnApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  getWatch(projectId: string): Observable<ScientificReturnWatch> {
    return this.http.get<ScientificReturnWatch>(this.url(`/projects/${projectId}/watch`));
  }

  activateWatch(projectId: string, reviewIntervalDays = 90): Observable<ScientificReturnWatch> {
    return this.http.post<ScientificReturnWatch>(this.url(`/projects/${projectId}/watch`), {
      reviewIntervalDays,
    });
  }

  changeWatchStatus(
    watchId: string,
    status: ScientificReturnWatchStatus,
  ): Observable<ScientificReturnWatch> {
    return this.http.patch<ScientificReturnWatch>(this.url(`/watches/${watchId}`), { status });
  }

  runWatch(watchId: string): Observable<ScientificReturnRun> {
    return this.http.post<ScientificReturnRun>(this.url(`/watches/${watchId}/runs`), {});
  }

  listRuns(watchId: string): Observable<ScientificReturnRunsPage> {
    return this.http.get<ScientificReturnRunsPage>(this.url(`/watches/${watchId}/runs`), {
      params: buildHttpParams({ page: 0, size: 10 }),
    });
  }

  listCandidates(
    projectId: string,
    status: ScientificReturnCandidateStatus | null,
  ): Observable<ScientificReturnCandidatesPage> {
    return this.http.get<ScientificReturnCandidatesPage>(
      this.url(`/projects/${projectId}/candidates`),
      { params: buildHttpParams({ status, page: 0, size: 50 }) },
    );
  }

  decideCandidate(
    candidateId: string,
    request: CandidateDecisionRequest,
  ): Observable<ScientificReturnCandidate> {
    return this.http.post<ScientificReturnCandidate>(
      this.url(`/candidates/${candidateId}/decision`),
      request,
    );
  }

  listDecisions(candidateId: string): Observable<readonly CandidateDecisionRecord[]> {
    return this.http.get<readonly CandidateDecisionRecord[]>(
      this.url(`/candidates/${candidateId}/decisions`),
    );
  }

  private url(path: string): string {
    return `${this.apiBaseUrl}/scientific-return${path}`;
  }
}
