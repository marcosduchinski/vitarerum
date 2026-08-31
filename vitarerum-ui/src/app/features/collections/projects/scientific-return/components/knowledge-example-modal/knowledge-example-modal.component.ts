import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  OnChanges,
  output,
  signal,
} from '@angular/core';
import { FormField, form, maxLength, pattern, required } from '@angular/forms/signals';

import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';

import { ScientificReturnKnowledgeItem } from '../../../models/scientific-return.model';

export interface KnowledgeExampleDraft {
  readonly content: string;
  readonly registeredNumber: string;
  readonly observedForm: string;
}

@Component({
  selector: 'app-knowledge-example-modal',
  standalone: true,
  imports: [ConfirmModalComponent, FormField],
  templateUrl: './knowledge-example-modal.component.html',
  styleUrl: './knowledge-example-modal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeExampleModalComponent implements OnChanges {
  readonly open = input(false);
  readonly item = input<ScientificReturnKnowledgeItem | null>(null);
  readonly pending = input(false);
  readonly saved = output<KnowledgeExampleDraft>();
  readonly cancelled = output<void>();

  protected readonly model = signal<KnowledgeExampleDraft>({
    content: '',
    registeredNumber: '',
    observedForm: '',
  });
  protected readonly exampleForm = form(this.model, (path) => {
    required(path.content, { message: 'Curatorial explanation is required.' });
    pattern(path.content, /\S/, { message: 'Curatorial explanation cannot be blank.' });
    maxLength(path.content, 4000, { message: 'Use at most 4000 characters.' });
    maxLength(path.registeredNumber, 255, { message: 'Use at most 255 characters.' });
    maxLength(path.observedForm, 255, { message: 'Use at most 255 characters.' });
  });
  protected readonly isInventoryExample = computed(() => this.item()?.kind !== 'CURATORIAL_LESSON');
  protected readonly invalid = computed(() => {
    const value = this.model();
    return (
      this.exampleForm().invalid() ||
      !value.content.trim() ||
      (this.isInventoryExample() && (!value.registeredNumber.trim() || !value.observedForm.trim()))
    );
  });

  ngOnChanges(): void {
    if (!this.open()) return;
    const item = this.item();
    this.model.set({
      content: item?.content ?? '',
      registeredNumber: item?.registeredNumber ?? '',
      observedForm: item?.observedForm ?? '',
    });
  }

  protected submit(): void {
    if (this.invalid() || this.pending()) return;
    const value = this.model();
    this.saved.emit({
      content: value.content.trim(),
      registeredNumber: value.registeredNumber.trim(),
      observedForm: value.observedForm.trim(),
    });
  }
}
