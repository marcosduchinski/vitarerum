import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '@core/config/app-config.model';

import {
  TestBatch,
  TestCandidate,
  TestItem,
  TestReadiness,
  TestSource,
  TestSourceWrite,
} from '../models/scientific-return-test.model';

@Injectable({ providedIn: 'root' })
export class ScientificReturnTestApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  readiness(): Observable<TestReadiness> {
    return this.http.get<TestReadiness>(this.url('/test-readiness'));
  }

  listSources(): Observable<readonly TestSource[]> {
    return this.http.get<readonly TestSource[]>(this.url('/test-sources'));
  }

  getSource(id: string): Observable<TestSource> {
    return this.http.get<TestSource>(this.url(`/test-sources/${id}`));
  }

  createSource(value: TestSourceWrite): Observable<TestSource> {
    return this.http.post<TestSource>(this.url('/test-sources'), value);
  }

  replaceSource(id: string, value: TestSourceWrite): Observable<TestSource> {
    return this.http.put<TestSource>(this.url(`/test-sources/${id}`), value);
  }

  retireSource(id: string): Observable<TestSource> {
    return this.http.delete<TestSource>(this.url(`/test-sources/${id}`));
  }

  activateSource(id: string): Observable<TestSource> {
    return this.http.post<TestSource>(this.url(`/test-sources/${id}/activate`), {});
  }

  listBatches(): Observable<readonly TestBatch[]> {
    return this.http.get<readonly TestBatch[]>(this.url('/test-batches'));
  }

  createBatch(name: string | null): Observable<TestBatch> {
    return this.http.post<TestBatch>(this.url('/test-batches'), { name });
  }

  getBatch(id: string): Observable<TestBatch> {
    return this.http.get<TestBatch>(this.url(`/test-batches/${id}`));
  }

  selectSources(id: string, sourceIds: readonly string[]): Observable<TestBatch> {
    return this.http.put<TestBatch>(this.url(`/test-batches/${id}`), { sourceIds });
  }

  addItems(
    id: string,
    items: readonly { author: string; objectName: string; inventoryNumber: string }[],
  ): Observable<TestBatch> {
    return this.http.post<TestBatch>(this.url(`/test-batches/${id}/items`), { items });
  }

  removeItem(batchId: string, itemId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/test-batches/${batchId}/items/${itemId}`));
  }

  startBatch(id: string): Observable<TestBatch> {
    return this.http.post<TestBatch>(
      this.url(`/test-batches/${id}/start`),
      {},
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
  }

  cancelBatch(id: string): Observable<TestBatch> {
    return this.http.post<TestBatch>(this.url(`/test-batches/${id}/cancel`), {});
  }

  retryItem(batchId: string, itemId: string): Observable<TestItem> {
    return this.http.post<TestItem>(this.url(`/test-batches/${batchId}/items/${itemId}/retry`), {});
  }

  candidates(id: string): Observable<readonly TestCandidate[]> {
    return this.http.get<readonly TestCandidate[]>(this.url(`/test-batches/${id}/candidates`));
  }

  exportCsv(id: string): Observable<Blob> {
    return this.http.get(this.url(`/test-batches/${id}/export.csv`), { responseType: 'blob' });
  }

  private url(path: string): string {
    return `${this.apiBaseUrl}/scientific-return${path}`;
  }
}
