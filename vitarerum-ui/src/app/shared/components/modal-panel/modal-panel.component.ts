import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';

let nextId = 0;

/**
 * Dialog shell for read-only detail panels.
 *
 * Content that only needs to be read — a history, an audit trail — has no
 * decision to confirm, so it does not belong in `app-confirm-modal` with its
 * confirm/cancel footer. This carries the backdrop, the heading and the single
 * way out, and leaves the body to the caller.
 */
@Component({
  selector: 'app-modal-panel',
  standalone: true,
  templateUrl: './modal-panel.component.html',
  styleUrl: './modal-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModalPanelComponent {
  readonly open = input(false);
  readonly title = input.required<string>();
  readonly eyebrow = input('');
  readonly subtitle = input('');
  readonly closeLabel = input('Close');

  readonly closed = output<void>();

  protected readonly titleId = `modal-panel-title-${(nextId += 1)}`;

  private readonly dialog = viewChild<ElementRef<HTMLElement>>('dialog');

  constructor() {
    // Without focus inside the dialog, Escape never reaches its handler and the
    // reader is left tabbing through the page behind the backdrop.
    effect(() => {
      if (this.open()) this.dialog()?.nativeElement.focus();
    });
  }
}
