import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { UseType } from '@shared/models/collection-use-status.model';

import {
  DocumentTemplate,
  DocumentTemplateMetadata,
} from '../models/document-template.model';
import { DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE } from '../services/document-template-management.service';

const USE_TYPE_OPTIONS: readonly { readonly value: UseType; readonly label: string }[] = [
  { value: 'IN_SITU_VISIT', label: 'In-situ visit' },
  { value: 'EXHIBITION', label: 'Exhibition' },
  { value: 'OTHER', label: 'Other' },
];

interface EditModel {
  title: string;
  description: string;
  mandatory: boolean;
  active: boolean;
  displayOrder: number;
}

interface TemplateGroup {
  readonly useType: UseType;
  readonly label: string;
  readonly templates: readonly DocumentTemplate[];
}

@Component({
  selector: 'app-document-templates-page',
  standalone: true,
  imports: [PageHeaderComponent, ErrorMessageComponent, LoadingStateComponent],
  templateUrl: './document-templates-page.component.html',
  styleUrl: './document-templates-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentTemplatesPageComponent {
  private readonly service = inject(DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE);
  private readonly document = inject(DOCUMENT);

  protected readonly useTypeOptions = USE_TYPE_OPTIONS;

  protected readonly templatesResource = resource({
    loader: () => firstValueFrom(this.service.list()),
  });

  protected readonly loading = computed(() => this.templatesResource.isLoading());
  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.templatesResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly groups = computed<TemplateGroup[]>(() => {
    const all = this.templatesResource.value() ?? [];
    return USE_TYPE_OPTIONS.map((option) => ({
      useType: option.value,
      label: option.label,
      templates: all
        .filter((t) => t.useType === option.value)
        .sort((a, b) => a.displayOrder - b.displayOrder || a.title.localeCompare(b.title)),
    })).filter((group) => group.templates.length > 0);
  });

  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);

  // ── Create form ──────────────────────────────────────────────────────────
  protected readonly newUseType = signal<UseType>('IN_SITU_VISIT');
  protected readonly newTitle = signal('');
  protected readonly newDescription = signal('');
  protected readonly newMandatory = signal(false);
  protected readonly newActive = signal(true);
  protected readonly newDisplayOrder = signal(0);
  protected readonly newFile = signal<File | null>(null);

  protected readonly canCreate = computed(
    () => !this.busy() && !!this.newTitle().trim() && this.newFile() !== null,
  );

  // ── Inline edit ────────────────────────────────────────────────────────────
  protected readonly editingId = signal<string | null>(null);
  protected readonly editModel = signal<EditModel | null>(null);

  protected setNewUseType(event: Event): void {
    this.newUseType.set((event.target as HTMLSelectElement).value as UseType);
  }

  protected setNewFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.newFile.set(input.files?.[0] ?? null);
  }

  protected async create(): Promise<void> {
    const file = this.newFile();
    if (!file || !this.newTitle().trim()) return;
    await this.run(async () => {
      await firstValueFrom(
        this.service.create({
          useType: this.newUseType(),
          title: this.newTitle().trim(),
          description: this.newDescription().trim(),
          mandatory: this.newMandatory(),
          active: this.newActive(),
          displayOrder: this.newDisplayOrder(),
          file,
        }),
      );
      this.resetCreateForm();
    });
  }

  protected startEdit(template: DocumentTemplate): void {
    this.editingId.set(template.id);
    this.editModel.set({
      title: template.title,
      description: template.description,
      mandatory: template.mandatory,
      active: template.active,
      displayOrder: template.displayOrder,
    });
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
    this.editModel.set(null);
  }

  protected patchEdit<K extends keyof EditModel>(key: K, value: EditModel[K]): void {
    const current = this.editModel();
    if (current) this.editModel.set({ ...current, [key]: value });
  }

  protected async saveEdit(id: string): Promise<void> {
    const model = this.editModel();
    if (!model || !model.title.trim()) return;
    const metadata: DocumentTemplateMetadata = {
      title: model.title.trim(),
      description: model.description.trim(),
      mandatory: model.mandatory,
      active: model.active,
      displayOrder: model.displayOrder,
    };
    await this.run(async () => {
      await firstValueFrom(this.service.updateMetadata(id, metadata));
      this.cancelEdit();
    });
  }

  protected async replaceFile(id: string, event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    await this.run(() => firstValueFrom(this.service.replaceFile(id, file)));
  }

  protected async remove(template: DocumentTemplate): Promise<void> {
    const confirmed = this.document.defaultView?.confirm(
      `Delete template "${template.title}"?`,
    );
    if (!confirmed) return;
    await this.run(() => firstValueFrom(this.service.remove(template.id)));
  }

  protected async download(template: DocumentTemplate): Promise<void> {
    this.actionError.set(null);
    try {
      const blob = await firstValueFrom(this.service.downloadFile(template.id));
      const url = URL.createObjectURL(blob);
      const anchor = this.document.createElement('a');
      anchor.href = url;
      anchor.download = template.fileName;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      this.actionError.set(toApiError(err));
    }
  }

  private async run(operation: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await operation();
      this.templatesResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }

  private resetCreateForm(): void {
    this.newTitle.set('');
    this.newDescription.set('');
    this.newMandatory.set(false);
    this.newActive.set(true);
    this.newDisplayOrder.set(0);
    this.newFile.set(null);
  }
}
