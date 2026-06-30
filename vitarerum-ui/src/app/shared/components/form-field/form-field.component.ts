import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  ViewEncapsulation,
} from '@angular/core';
import { Field } from '@angular/forms/signals';

/**
 * Wraps a Signal Forms control with its label and validation message, and
 * toggles an invalid border state once the field has been touched. The actual
 * `<input>`/`<textarea>` (with its `[formField]` binding) is projected so the
 * consumer keeps full control of the control element.
 *
 * Unencapsulated so the shared field styling reaches the projected control.
 */
@Component({
  selector: 'app-form-field',
  standalone: true,
  templateUrl: './form-field.component.html',
  styleUrl: './form-field.component.scss',
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FormFieldComponent {
  readonly label = input.required<string>();
  readonly controlId = input.required<string>();
  readonly field = input.required<Field<string>>();

  protected readonly state = computed(() => this.field()());
  protected readonly invalid = computed(
    () => this.state().touched() && this.state().invalid(),
  );
  protected readonly firstError = computed(() => this.state().errors()[0]?.message ?? '');
}
