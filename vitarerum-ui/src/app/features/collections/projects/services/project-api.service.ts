import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Page } from '@shared/models/page.model';
import { map, Observable } from 'rxjs';

import {
  Attachment,
  CollectionUseProjectDetail,
  CollectionUseProjectSummary,
  CreateObjectLogEntryRequest,
  CreateObjectOccurrenceEntryRequest,
  NoteRequest,
  ObjectAccessLog,
  ObjectLogEntriesPage,
  ObjectLogEntriesQuery,
  ObjectLogEntry,
  ObjectOccurrenceEntriesPage,
  ObjectOccurrenceEntriesQuery,
  ObjectOccurrenceEntry,
  ObjectOccurrenceLog,
  ProjectEventsPage,
  ProjectEventsQuery,
  ProjectListQuery,
  PublicationEntriesPage,
  PublicationEntriesQuery,
  PublicationLog,
  PublicationLogEntry,
  ReasonRequest,
  UpdateObjectLogEntryRequest,
  UpdateObjectOccurrenceEntryRequest,
  UseEvent,
} from '../models/project.model';
import { MediaType, UseResult, UseStatus } from '@shared/models/collection-use-status.model';

export interface ProjectTransitionResult {
  readonly id: string;
  readonly referenceNumber: string;
  readonly status: UseStatus;
  readonly result: UseResult | null;
  readonly lastEvent: UseEvent;
}

// The backend returns the use type wrapped as `intendedUse: { useType, description }`.
// Bridge it to the flat `type` the app reads, tolerating either shape.
function normalizeProjectType<T extends CollectionUseProjectSummary>(p: T): T {
  if (p.type) return p;
  const useType = p.intendedUse?.useType;
  return useType ? { ...p, type: useType } : p;
}

export const PROJECT_API_SERVICE = new InjectionToken<ProjectApiService>('PROJECT_API_SERVICE');

@Injectable()
export class ProjectApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listProjects(query: ProjectListQuery = {}): Observable<Page<CollectionUseProjectSummary>> {
    const serverQuery = { ...query };
    // `requestedBy` is now an honored server-side filter (staff-only; non-staff
    // callers are auto-scoped to their own permissionId regardless). `assignedTo`
    // is still not implemented by the backend, so keep stripping it.
    delete serverQuery.assignedTo;
    return this.http
      .get<Page<CollectionUseProjectSummary>>(this.url('/collection-use-projects'), {
        params: buildHttpParams(serverQuery),
      })
      .pipe(
        map((page) => ({ ...page, content: page.content.map((p) => normalizeProjectType(p)) })),
      );
  }

  getProject(projectId: string): Observable<CollectionUseProjectDetail> {
    return this.http
      .get<CollectionUseProjectDetail>(this.url(`/collection-use-projects/${projectId}`))
      .pipe(map((p) => normalizeProjectType(p)));
  }

  startProject(projectId: string, request: NoteRequest): Observable<ProjectTransitionResult> {
    return this.http.post<ProjectTransitionResult>(
      this.url(`/collection-use-projects/${projectId}/start`),
      request,
    );
  }

  completeProject(projectId: string, request: NoteRequest): Observable<ProjectTransitionResult> {
    return this.http.post<ProjectTransitionResult>(
      this.url(`/collection-use-projects/${projectId}/complete`),
      request,
    );
  }

  cancelProject(projectId: string, request: ReasonRequest): Observable<ProjectTransitionResult> {
    return this.http.post<ProjectTransitionResult>(
      this.url(`/collection-use-projects/${projectId}/cancel`),
      request,
    );
  }

  createObjectLogEntry(
    projectId: string,
    request: CreateObjectLogEntryRequest,
  ): Observable<ObjectLogEntry> {
    return this.http.post<ObjectLogEntry>(
      this.url(`/collection-use-projects/${projectId}/log-entries`),
      request,
    );
  }

  listObjectLogEntries(
    projectId: string,
    query: ObjectLogEntriesQuery = {},
  ): Observable<ObjectLogEntriesPage> {
    return this.http.get<ObjectLogEntriesPage>(
      this.url(`/collection-use-projects/${projectId}/log-entries`),
      { params: buildHttpParams(query) },
    );
  }

  updateObjectLogEntry(
    projectId: string,
    entryId: string,
    request: UpdateObjectLogEntryRequest,
  ): Observable<ObjectLogEntry> {
    return this.http.patch<ObjectLogEntry>(
      this.url(`/collection-use-projects/${projectId}/log-entries/${entryId}`),
      request,
    );
  }

  getObjectAccessLog(projectId: string): Observable<ObjectAccessLog> {
    return this.http.get<ObjectAccessLog>(
      this.url(`/collection-use-projects/${projectId}/object-access-log`),
    );
  }

  uploadLogEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
  ): Observable<Attachment> {
    const body = new FormData();
    body.append('file', file);
    body.append('mediaType', mediaType);

    return this.http.post<Attachment>(
      this.url(`/collection-use-projects/${projectId}/log-entries/${entryId}/attachments`),
      body,
    );
  }

  // Downloads a log-entry attachment's binary content. The endpoint streams the
  // file (Content-Disposition: attachment); the Bearer token is added by the
  // auth interceptor, so it must be fetched here rather than linked directly.
  downloadLogEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    return this.http.get(
      this.url(
        `/collection-use-projects/${projectId}/log-entries/${entryId}/attachments/${encodeURIComponent(
          fileReference,
        )}`,
      ),
      { responseType: 'blob' },
    );
  }

  createObjectOccurrenceEntry(
    projectId: string,
    request: CreateObjectOccurrenceEntryRequest,
  ): Observable<ObjectOccurrenceEntry> {
    return this.http.post<ObjectOccurrenceEntry>(
      this.url(`/collection-use-projects/${projectId}/occurrence-entries`),
      request,
    );
  }

  listObjectOccurrenceEntries(
    projectId: string,
    query: ObjectOccurrenceEntriesQuery = {},
  ): Observable<ObjectOccurrenceEntriesPage> {
    return this.http.get<ObjectOccurrenceEntriesPage>(
      this.url(`/collection-use-projects/${projectId}/occurrence-entries`),
      { params: buildHttpParams(query) },
    );
  }

  updateObjectOccurrenceEntry(
    projectId: string,
    entryId: string,
    request: UpdateObjectOccurrenceEntryRequest,
  ): Observable<ObjectOccurrenceEntry> {
    return this.http.patch<ObjectOccurrenceEntry>(
      this.url(`/collection-use-projects/${projectId}/occurrence-entries/${entryId}`),
      request,
    );
  }

  getObjectOccurrenceLog(projectId: string): Observable<ObjectOccurrenceLog> {
    return this.http.get<ObjectOccurrenceLog>(
      this.url(`/collection-use-projects/${projectId}/object-occurrence-log`),
    );
  }

  uploadOccurrenceEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
  ): Observable<Attachment> {
    const body = new FormData();
    body.append('file', file);
    body.append('mediaType', mediaType);

    return this.http.post<Attachment>(
      this.url(`/collection-use-projects/${projectId}/occurrence-entries/${entryId}/attachments`),
      body,
    );
  }

  // Downloads an occurrence-entry attachment's binary content. Same streaming
  // contract as the log-entry attachment download.
  downloadOccurrenceEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    return this.http.get(
      this.url(
        `/collection-use-projects/${projectId}/occurrence-entries/${entryId}/attachments/${encodeURIComponent(
          fileReference,
        )}`,
      ),
      { responseType: 'blob' },
    );
  }

  createPublicationEntry(projectId: string, request: NoteRequest): Observable<PublicationLogEntry> {
    return this.http.post<PublicationLogEntry>(
      this.url(`/collection-use-projects/${projectId}/publication-entries`),
      request,
    );
  }

  listPublicationEntries(
    projectId: string,
    query: PublicationEntriesQuery = {},
  ): Observable<PublicationEntriesPage> {
    return this.http.get<PublicationEntriesPage>(
      this.url(`/collection-use-projects/${projectId}/publication-entries`),
      { params: buildHttpParams(query) },
    );
  }

  updatePublicationEntry(
    projectId: string,
    entryId: string,
    request: NoteRequest,
  ): Observable<PublicationLogEntry> {
    return this.http.patch<PublicationLogEntry>(
      this.url(`/collection-use-projects/${projectId}/publication-entries/${entryId}`),
      request,
    );
  }

  getPublicationLog(projectId: string): Observable<PublicationLog> {
    return this.http.get<PublicationLog>(
      this.url(`/collection-use-projects/${projectId}/publication-log`),
    );
  }

  uploadPublicationEntryAttachment(
    projectId: string,
    entryId: string,
    file: File,
    mediaType: MediaType,
    note?: string,
  ): Observable<Attachment> {
    const body = new FormData();
    body.append('file', file);
    body.append('mediaType', mediaType);
    if (note) body.append('note', note);

    return this.http.post<Attachment>(
      this.url(`/collection-use-projects/${projectId}/publication-entries/${entryId}/attachments`),
      body,
    );
  }

  // Downloads a publication-entry attachment's binary content. Same streaming
  // contract as the log-entry attachment download.
  downloadPublicationEntryAttachment(
    projectId: string,
    entryId: string,
    fileReference: string,
  ): Observable<Blob> {
    return this.http.get(
      this.url(
        `/collection-use-projects/${projectId}/publication-entries/${entryId}/attachments/${encodeURIComponent(
          fileReference,
        )}`,
      ),
      { responseType: 'blob' },
    );
  }

  listEvents(projectId: string, query: ProjectEventsQuery = {}): Observable<ProjectEventsPage> {
    return this.http.get<ProjectEventsPage>(
      this.url(`/collection-use-projects/${projectId}/events`),
      {
        params: buildHttpParams(query),
      },
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
