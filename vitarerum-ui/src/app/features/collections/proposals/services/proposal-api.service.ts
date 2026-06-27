import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Page, PageQuery } from '@shared/models/page.model';
import { map, Observable } from 'rxjs';

import {
  AddRequestedObjectsRequest,
  ApproveProposalRequest,
  AssignProposalRequest,
  ForwardProposalRequest,
  ProposalAssignmentResult,
  ProposalCancellationResult,
  ProposalDecisionResult,
  ProposalReasonRequest,
  UpdateProposalRequest,
} from '../models/proposal-actions.model';
import {
  Conversation,
  CreateProposalRequest,
  CreateProposalResponse,
  Document,
  Message,
  ProposalDetail,
  ProposalDocumentsResponse,
  ProposalEventsPage,
  ProposalListQuery,
  ProposalSummary,
  SendMessageRequest,
  UpdateProposalResult,
} from '../models/proposal.model';

// The backend returns the use type wrapped as `intendedUse: { useType, description }`.
// Bridge it to the flat `type` the app reads, tolerating either shape.
function normalizeProposalType<T extends ProposalSummary>(p: T): T {
  if (p.type) return p;
  const useType = p.intendedUse?.useType;
  return { ...p, type: useType ?? 'OTHER' };
}

export const PROPOSAL_API_SERVICE = new InjectionToken<ProposalApiService>('PROPOSAL_API_SERVICE');

@Injectable()
export class ProposalApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  createProposal(request: CreateProposalRequest): Observable<CreateProposalResponse> {
    return this.http.post<CreateProposalResponse>(this.url('/proposals'), request);
  }

  listProposals(query: ProposalListQuery = {}): Observable<Page<ProposalSummary>> {
    // The contract uses snake_case filter names; the TS query stays camelCase.
    const statuses = typeof query.status === 'string' ? [query.status] : (query.status ?? []);
    let params = statuses.reduce(
      (httpParams, status) => httpParams.append('status', status),
      buildHttpParams({}),
    );
    const remainingParams = buildHttpParams({
      type: query.type,
      requested_by: query.requestedBy,
      assigned_to: query.assignedTo,
      date_from: query.dateFrom,
      date_to: query.dateTo,
      search: query.search,
      page: query.page,
      size: query.size,
    });
    for (const key of remainingParams.keys()) {
      for (const value of remainingParams.getAll(key) ?? []) {
        params = params.append(key, value);
      }
    }

    return this.http
      .get<Page<ProposalSummary>>(this.url('/proposals'), {
        params,
      })
      .pipe(
        map((page) => ({ ...page, content: page.content.map((p) => normalizeProposalType(p)) })),
      );
  }

  getProposal(proposalId: string): Observable<ProposalDetail> {
    return this.http
      .get<ProposalDetail>(this.url(`/proposals/${proposalId}`))
      .pipe(map((p) => normalizeProposalType(p)));
  }

  updateProposal(
    proposalId: string,
    request: UpdateProposalRequest,
  ): Observable<UpdateProposalResult> {
    return this.http.patch<UpdateProposalResult>(this.url(`/proposals/${proposalId}`), request);
  }

  addRequestedObjects(
    proposalId: string,
    request: AddRequestedObjectsRequest,
  ): Observable<ProposalDetail> {
    return this.http.post<ProposalDetail>(
      this.url(`/proposals/${proposalId}/requested-objects`),
      request,
    );
  }

  uploadDocument(proposalId: string, file: File, documentType: string): Observable<Document> {
    const body = new FormData();
    body.append('file', file);
    body.append('documentType', documentType);

    return this.http.post<Document>(this.url(`/proposals/${proposalId}/documents`), body);
  }

  listDocuments(proposalId: string): Observable<ProposalDocumentsResponse> {
    return this.http.get<ProposalDocumentsResponse>(this.url(`/proposals/${proposalId}/documents`));
  }

  // Downloads a single document's binary content. The endpoint streams the file
  // (Content-Disposition: attachment); the Bearer token is added by the auth
  // interceptor, so it must be fetched here rather than linked directly.
  downloadDocument(proposalId: string, documentId: string): Observable<Blob> {
    return this.http.get(this.url(`/proposals/${proposalId}/documents/${documentId}`), {
      responseType: 'blob',
    });
  }

  listEvents(proposalId: string, query: PageQuery = {}): Observable<ProposalEventsPage> {
    return this.http.get<ProposalEventsPage>(this.url(`/proposals/${proposalId}/events`), {
      params: buildHttpParams(query),
    });
  }

  getConversation(proposalId: string, query: PageQuery = {}): Observable<Conversation> {
    return this.http.get<Conversation>(this.url(`/proposals/${proposalId}/conversation`), {
      params: buildHttpParams(query),
    });
  }

  sendMessage(proposalId: string, request: SendMessageRequest): Observable<Message> {
    return this.http.post<Message>(
      this.url(`/proposals/${proposalId}/conversation/messages`),
      request,
    );
  }

  assignProposal(
    proposalId: string,
    request: AssignProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/assign`),
      request,
    );
  }

  forwardProposal(
    proposalId: string,
    request: ForwardProposalRequest,
  ): Observable<ProposalAssignmentResult> {
    return this.http.post<ProposalAssignmentResult>(
      this.url(`/proposals/${proposalId}/forward`),
      request,
    );
  }

  approveProposal(
    proposalId: string,
    request: ApproveProposalRequest,
  ): Observable<ProposalDecisionResult> {
    return this.http.post<ProposalDecisionResult>(
      this.url(`/proposals/${proposalId}/approve`),
      request,
    );
  }

  rejectProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalDecisionResult> {
    return this.http.post<ProposalDecisionResult>(
      this.url(`/proposals/${proposalId}/reject`),
      request,
    );
  }

  // Researcher cancels their own proposal. Allowed from SUBMITTED/PENDING/APPROVED;
  // a linked project (if any) is cascaded to CANCELLED by the backend.
  cancelProposal(
    proposalId: string,
    request: ProposalReasonRequest,
  ): Observable<ProposalCancellationResult> {
    return this.http.post<ProposalCancellationResult>(
      this.url(`/proposals/${proposalId}/cancel`),
      request,
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
