import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { FormField, form, maxLength, required } from '@angular/forms/signals';

import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { TestSourceKind } from '../../models/scientific-return-test.model';
import { ScientificReturnTestFacade } from './state/scientific-return-test.facade';

interface SourceFormModel {
  name: string;
  kind: TestSourceKind;
  locator: string;
  authors: string;
  content: string;
}

interface ItemFormModel {
  author: string;
  objectName: string;
  inventoryNumber: string;
}

const EMPTY_SOURCE: SourceFormModel = {
  name: '',
  kind: 'TEXT_DOCUMENT',
  locator: '',
  authors: '',
  content: '',
};
const EMPTY_ITEM: ItemFormModel = { author: '', objectName: '', inventoryNumber: '' };

@Component({
  selector: 'app-scientific-return-test-page',
  standalone: true,
  imports: [FormField, PageHeaderComponent],
  providers: [ScientificReturnTestFacade],
  templateUrl: './scientific-return-test-page.component.html',
  styleUrl: './scientific-return-test-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScientificReturnTestPageComponent implements OnInit {
  protected readonly facade = inject(ScientificReturnTestFacade);
  protected readonly sourceModel = signal<SourceFormModel>({ ...EMPTY_SOURCE });
  protected readonly itemModel = signal<ItemFormModel>({ ...EMPTY_ITEM });
  protected readonly batchName = signal('');
  protected readonly editingSourceId = signal<string | null>(null);
  protected readonly resultSourceFilter = signal('ALL');
  protected readonly resultEvidenceFilter = signal('ALL');
  protected readonly filteredCandidates = computed(() =>
    this.facade
      .candidates()
      .filter(
        (candidate) =>
          (this.resultSourceFilter() === 'ALL' ||
            candidate.sourceId === this.resultSourceFilter()) &&
          (this.resultEvidenceFilter() === 'ALL' ||
            candidate.inventoryEvidenceStatus === this.resultEvidenceFilter()),
      ),
  );

  // Signal Forms is experimental in Angular 21; both forms stay local to this page.
  protected readonly sourceForm = form(this.sourceModel, (path) => {
    required(path.name, { message: 'Source name is required.' });
    maxLength(path.name, 255);
    required(path.content, { message: 'Searchable content is required.' });
    maxLength(path.content, 100_000);
  });
  protected readonly itemForm = form(this.itemModel, (path) => {
    required(path.author, { message: 'Author is required.' });
    required(path.objectName, { message: 'Object name is required.' });
    required(path.inventoryNumber, { message: 'Inventory number is required.' });
  });

  ngOnInit(): void {
    void this.facade.initialize();
  }

  protected async saveSource(event: Event): Promise<void> {
    event.preventDefault();
    this.sourceForm().markAsTouched();
    if (this.sourceForm().invalid()) return;
    const value = this.sourceModel();
    await this.facade.saveSource(
      {
        name: value.name,
        kind: value.kind,
        locator: value.locator.trim() || null,
        authors: value.authors
          .split(',')
          .map((author) => author.trim())
          .filter(Boolean),
        content: value.content,
      },
      this.editingSourceId(),
    );
    this.cancelSourceEdit();
  }

  protected async editSource(id: string): Promise<void> {
    const source = await this.facade.getSource(id);
    const revision = source?.revisions?.[0];
    if (!source || !revision) return;
    this.editingSourceId.set(id);
    this.sourceModel.set({
      name: source.name,
      kind: source.kind,
      locator: revision.locator ?? '',
      authors: revision.authors.join(', '),
      content: revision.content,
    });
  }

  protected cancelSourceEdit(): void {
    this.editingSourceId.set(null);
    this.sourceModel.set({ ...EMPTY_SOURCE });
    this.sourceForm().reset();
  }

  protected async addItem(event: Event): Promise<void> {
    event.preventDefault();
    this.itemForm().markAsTouched();
    if (this.itemForm().invalid()) return;
    await this.facade.addItem(this.itemModel());
    this.itemModel.set({ ...EMPTY_ITEM });
    this.itemForm().reset();
  }

  protected sourceSelected(id: string): boolean {
    return this.facade.batch()?.sourceIds.includes(id) ?? false;
  }

  protected isWorking(): boolean {
    const status = this.facade.batch()?.status;
    return status === 'QUEUED' || status === 'RUNNING' || status === 'CANCELLING';
  }
}
