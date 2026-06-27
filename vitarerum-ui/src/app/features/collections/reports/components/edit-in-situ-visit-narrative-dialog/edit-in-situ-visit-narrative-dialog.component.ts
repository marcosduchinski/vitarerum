import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormField, form, pattern, required } from '@angular/forms/signals';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';

import { InSituVisitReportNarrative } from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

interface NarrativeEditorModel {
  readonly narrative: string;
}

@Component({
  selector: 'app-edit-in-situ-visit-narrative-dialog',
  standalone: true,
  imports: [FormField, ErrorMessageComponent],
  templateUrl: './edit-in-situ-visit-narrative-dialog.component.html',
  styleUrl: './edit-in-situ-visit-narrative-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EditInSituVisitNarrativeDialogComponent {
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('dialog');
  private readonly textarea = viewChild<ElementRef<HTMLTextAreaElement>>('textarea');
  private loadedNarrativeId: string | null = null;

  readonly open = input(false);
  readonly narrative = input<InSituVisitReportNarrative | null>(null);

  readonly closed = output<void>();
  readonly saved = output<InSituVisitReportNarrative>();

  protected readonly formModel = signal<NarrativeEditorModel>({ narrative: '' });
  // Signal Forms is experimental in Angular 21. Keeping it local to this editor
  // limits the migration surface if its API changes.
  protected readonly editorForm = form(this.formModel, (path) => {
    required(path.narrative, { message: 'Narrative text is required.' });
    pattern(path.narrative, /\S/, { message: 'Narrative text cannot be blank.' });
  });
  protected readonly pending = signal(false);
  protected readonly apiError = signal<ApiError | null>(null);
  protected readonly discardConfirmation = signal(false);
  protected readonly characterCount = computed(() => this.formModel().narrative.length);
  protected readonly changed = computed(() => {
    const original = this.narrative()?.text.trim() ?? '';
    return this.formModel().narrative.trim() !== original;
  });
  protected readonly saveDisabled = computed(
    () => this.pending() || !this.narrative() || !this.changed() || this.editorForm().invalid(),
  );

  private readonly syncDraft = effect(() => {
    const open = this.open();
    const narrative = this.narrative();

    if (!open) {
      this.loadedNarrativeId = null;
      return;
    }
    if (!narrative || this.loadedNarrativeId === narrative.narrativeId) return;

    this.loadedNarrativeId = narrative.narrativeId;
    this.formModel.set({ narrative: narrative.text });
    this.apiError.set(null);
    this.discardConfirmation.set(false);
  });

  private readonly syncNativeDialog = effect(() => {
    const dialog = this.dialog()?.nativeElement;
    if (!dialog) return;

    if (this.open() && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    } else if (!this.open() && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
  });

  protected async submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    this.editorForm().markAsTouched();
    this.editorForm.narrative().markAsTouched();
    const narrative = this.narrative();
    const replacement = this.formModel().narrative.trim();
    if (!narrative || this.saveDisabled() || !replacement) return;

    this.pending.set(true);
    this.apiError.set(null);
    try {
      const updated = await firstValueFrom(
        this.reportsService.updateInSituVisitNarrative(narrative.recordId, narrative.narrativeId, {
          narrative: replacement,
        }),
      );
      this.saved.emit(updated);
    } catch (error) {
      this.apiError.set(toApiError(error));
    } finally {
      this.pending.set(false);
    }
  }

  protected requestClose(): void {
    if (this.pending()) return;
    if (this.changed()) {
      this.discardConfirmation.set(true);
      return;
    }
    this.closed.emit();
  }

  protected onCancel(event: Event): void {
    event.preventDefault();
    this.requestClose();
  }

  protected onBackdropClick(event: MouseEvent): void {
    if (event.target === this.dialog()?.nativeElement) this.requestClose();
  }

  protected keepEditing(): void {
    this.discardConfirmation.set(false);
    this.textarea()?.nativeElement.focus();
  }

  protected confirmDiscard(): void {
    if (this.pending()) return;
    this.discardConfirmation.set(false);
    this.apiError.set(null);
    this.formModel.set({ narrative: this.narrative()?.text ?? '' });
    this.closed.emit();
  }
}
