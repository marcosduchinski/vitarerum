import { computed, effect, inject, Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';

import {
  TestBatch,
  TestCandidate,
  TestReadiness,
  TestSource,
  TestSourceWrite,
} from '../../../models/scientific-return-test.model';
import { ScientificReturnTestApiService } from '../../../services/scientific-return-test-api.service';

const TERMINAL = new Set(['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED']);

@Injectable()
export class ScientificReturnTestFacade {
  private readonly api = inject(ScientificReturnTestApiService);
  private readonly sourcesState = signal<readonly TestSource[]>([]);
  private readonly batchesState = signal<readonly TestBatch[]>([]);
  private readonly batchState = signal<TestBatch | null>(null);
  private readonly candidatesState = signal<readonly TestCandidate[]>([]);
  private readonly readinessState = signal<TestReadiness | null>(null);
  private readonly busyState = signal(false);
  private readonly errorState = signal<ApiError | null>(null);

  readonly sources = this.sourcesState.asReadonly();
  readonly batches = this.batchesState.asReadonly();
  readonly batch = this.batchState.asReadonly();
  readonly candidates = this.candidatesState.asReadonly();
  readonly readiness = this.readinessState.asReadonly();
  readonly busy = this.busyState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly activeSources = computed(() =>
    this.sources().filter((source) => source.status === 'ACTIVE'),
  );
  readonly canStart = computed(() => {
    const batch = this.batch();
    const readiness = this.readiness();
    return Boolean(
      batch?.status === 'DRAFT' &&
      batch.items.length > 0 &&
      batch.sourceIds.length > 0 &&
      readiness?.enabled &&
      readiness.configurationValid &&
      !this.busy(),
    );
  });

  constructor() {
    effect((onCleanup) => {
      const batch = this.batch();
      if (!batch || TERMINAL.has(batch.status)) return;
      const refresh = (): void => {
        if (document.visibilityState === 'visible') void this.refreshBatch(false);
      };
      const timer = window.setInterval(refresh, 3_000);
      onCleanup(() => window.clearInterval(timer));
    });
  }

  async initialize(): Promise<void> {
    await this.run(async () => {
      const [sources, batches, readiness] = await Promise.all([
        firstValueFrom(this.api.listSources()),
        firstValueFrom(this.api.listBatches()),
        firstValueFrom(this.api.readiness()),
      ]);
      this.sourcesState.set(sources);
      this.batchesState.set(batches);
      this.readinessState.set(readiness);
      if (batches[0]) await this.openBatch(batches[0].id);
    });
  }

  async saveSource(value: TestSourceWrite, id: string | null = null): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(id ? this.api.replaceSource(id, value) : this.api.createSource(value));
      this.sourcesState.set(await firstValueFrom(this.api.listSources()));
    });
  }

  async getSource(id: string): Promise<TestSource | null> {
    try {
      return await firstValueFrom(this.api.getSource(id));
    } catch (error) {
      this.errorState.set(toApiError(error));
      return null;
    }
  }

  async toggleSource(source: TestSource): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(
        source.status === 'ACTIVE'
          ? this.api.retireSource(source.id)
          : this.api.activateSource(source.id),
      );
      this.sourcesState.set(await firstValueFrom(this.api.listSources()));
    });
  }

  async createBatch(name: string): Promise<void> {
    await this.run(async () => {
      const batch = await firstValueFrom(this.api.createBatch(name.trim() || null));
      this.batchState.set(batch);
      this.candidatesState.set([]);
      this.batchesState.set(await firstValueFrom(this.api.listBatches()));
    });
  }

  async duplicateBatch(): Promise<void> {
    const original = this.batch();
    if (!original) return;
    await this.run(async () => {
      let duplicate = await firstValueFrom(
        this.api.createBatch(`Copy of ${original.name ?? 'test batch'}`),
      );
      duplicate = await firstValueFrom(this.api.selectSources(duplicate.id, original.sourceIds));
      if (original.items.length) {
        duplicate = await firstValueFrom(
          this.api.addItems(
            duplicate.id,
            original.items.map((item) => ({
              author: item.author,
              objectName: item.objectName,
              inventoryNumber: item.inventoryNumber,
            })),
          ),
        );
      }
      this.batchState.set(duplicate);
      this.candidatesState.set([]);
      this.batchesState.set(await firstValueFrom(this.api.listBatches()));
    });
  }

  async openBatch(id: string): Promise<void> {
    await this.run(async () => {
      const batch = await firstValueFrom(this.api.getBatch(id));
      this.batchState.set(batch);
      this.candidatesState.set(await firstValueFrom(this.api.candidates(id)));
    });
  }

  async setSourceSelected(sourceId: string, selected: boolean): Promise<void> {
    const batch = this.batch();
    if (!batch || batch.status !== 'DRAFT') return;
    const ids = selected
      ? [...new Set([...batch.sourceIds, sourceId])]
      : batch.sourceIds.filter((id) => id !== sourceId);
    await this.run(async () =>
      this.batchState.set(await firstValueFrom(this.api.selectSources(batch.id, ids))),
    );
  }

  async addItem(value: {
    author: string;
    objectName: string;
    inventoryNumber: string;
  }): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    await this.run(async () =>
      this.batchState.set(await firstValueFrom(this.api.addItems(batch.id, [value]))),
    );
  }

  async removeItem(itemId: string): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    await this.run(async () => {
      await firstValueFrom(this.api.removeItem(batch.id, itemId));
      await this.refreshBatch(false);
    });
  }

  async start(): Promise<void> {
    const batch = this.batch();
    if (!batch || !this.canStart()) return;
    await this.run(async () =>
      this.batchState.set(await firstValueFrom(this.api.startBatch(batch.id))),
    );
  }

  async cancel(): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    await this.run(async () =>
      this.batchState.set(await firstValueFrom(this.api.cancelBatch(batch.id))),
    );
  }

  async retry(itemId: string): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    await this.run(async () => {
      await firstValueFrom(this.api.retryItem(batch.id, itemId));
      await this.refreshBatch(false);
    });
  }

  async download(): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    await this.run(async () => {
      const blob = await firstValueFrom(this.api.exportCsv(batch.id));
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `scientific-return-test-${batch.id}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }

  private async refreshBatch(showBusy: boolean): Promise<void> {
    const batch = this.batch();
    if (!batch) return;
    if (showBusy) this.busyState.set(true);
    try {
      const refreshed = await firstValueFrom(this.api.getBatch(batch.id));
      this.batchState.set(refreshed);
      this.candidatesState.set(await firstValueFrom(this.api.candidates(batch.id)));
    } finally {
      if (showBusy) this.busyState.set(false);
    }
  }

  private async run(operation: () => Promise<void>): Promise<void> {
    this.busyState.set(true);
    this.errorState.set(null);
    try {
      await operation();
    } catch (error) {
      this.errorState.set(toApiError(error));
    } finally {
      this.busyState.set(false);
    }
  }
}
