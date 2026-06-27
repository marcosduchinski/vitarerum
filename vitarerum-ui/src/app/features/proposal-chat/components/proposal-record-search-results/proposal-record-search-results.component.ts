import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  linkedSignal,
  output,
} from '@angular/core';

import { ApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';

import { CatalogRecordSnapshot } from '../../models/proposal-chat.model';

@Component({
  selector: 'app-proposal-record-search-results',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ErrorMessageComponent, FeedbackMessageComponent],
  templateUrl: './proposal-record-search-results.component.html',
  styleUrl: './proposal-record-search-results.component.scss',
})
export class ProposalRecordSearchResultsComponent {
  readonly records = input.required<readonly CatalogRecordSnapshot[]>();
  readonly submissionAllowed = input(true);
  readonly pending = input(false);
  readonly saved = input(false);
  readonly apiError = input<ApiError | null>(null);
  readonly submitted = output<readonly CatalogRecordSnapshot[]>();

  protected readonly selectedInventoryNumbers = linkedSignal<ReadonlySet<string>>(() => {
    this.records();
    return new Set<string>();
  });
  protected readonly selectedRecords = computed(() =>
    this.records().filter((record) => this.selectedInventoryNumbers().has(record.inventoryNumber)),
  );

  protected setSelected(inventoryNumber: string, event: Event): void {
    const selected = (event.target as HTMLInputElement).checked;
    this.selectedInventoryNumbers.update((current) => {
      const next = new Set(current);
      if (selected) next.add(inventoryNumber);
      else next.delete(inventoryNumber);
      return next;
    });
  }

  protected submit(): void {
    const selected = this.selectedRecords();
    if (!selected.length || this.pending() || this.saved() || !this.submissionAllowed()) return;
    this.submitted.emit(selected);
  }
}
