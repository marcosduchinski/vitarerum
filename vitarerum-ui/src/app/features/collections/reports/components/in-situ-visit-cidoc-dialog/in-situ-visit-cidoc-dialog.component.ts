import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  resource,
  signal,
  viewChild,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

type CopyStatus = 'idle' | 'copied' | 'error';

@Component({
  selector: 'app-in-situ-visit-cidoc-dialog',
  standalone: true,
  imports: [ErrorMessageComponent, LoadingStateComponent],
  templateUrl: './in-situ-visit-cidoc-dialog.component.html',
  styleUrl: './in-situ-visit-cidoc-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitCidocDialogComponent {
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly document = inject(DOCUMENT);
  private readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('dialog');

  readonly open = input(false);
  readonly recordId = input<string | null>(null);
  readonly closed = output<void>();

  protected readonly copyStatus = signal<CopyStatus>('idle');
  protected readonly cidocResource = resource({
    params: () => {
      const recordId = this.recordId();
      return this.open() && recordId ? { recordId } : undefined;
    },
    loader: ({ params }) =>
      firstValueFrom(this.reportsService.getInSituVisitCidocCrm(params.recordId)),
  });
  protected readonly formattedDocument = computed(() => {
    if (!this.cidocResource.hasValue()) return '';
    const value = this.cidocResource.value();
    return JSON.stringify(value, null, 2);
  });
  protected readonly cidocError = computed<ApiError | null>(() => {
    const error = this.cidocResource.error();
    return error ? toApiError(error) : null;
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

  protected requestClose(): void {
    this.copyStatus.set('idle');
    this.closed.emit();
  }

  protected onCancel(event: Event): void {
    event.preventDefault();
    this.requestClose();
  }

  protected onBackdropClick(event: MouseEvent): void {
    if (event.target === this.dialog()?.nativeElement) this.requestClose();
  }

  protected retry(): void {
    this.copyStatus.set('idle');
    this.cidocResource.reload();
  }

  protected async copyDocument(): Promise<void> {
    const text = this.formattedDocument();
    const clipboard = this.document.defaultView?.navigator.clipboard;
    if (!text || !clipboard) {
      this.copyStatus.set('error');
      return;
    }

    try {
      await clipboard.writeText(text);
      this.copyStatus.set('copied');
    } catch {
      this.copyStatus.set('error');
    }
  }
}
