import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
} from '@angular/core';
import { ButtonDirective } from 'primeng/button';

@Component({
  selector: 'app-pagination',
  standalone: true,
  imports: [ButtonDirective],
  templateUrl: './pagination.component.html',
  styleUrl: './pagination.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PaginationComponent {
  /** Zero-based current page index. */
  readonly page = input.required<number>();
  readonly totalPages = input.required<number>();
  readonly total = input.required<number>();
  readonly pageSize = input.required<number>();
  readonly itemLabel = input('items');

  readonly previous = output<void>();
  readonly next = output<void>();

  protected readonly rangeStart = computed(() =>
    this.total() === 0 ? 0 : this.page() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.page() + 1) * this.pageSize(), this.total()),
  );
  protected readonly isFirst = computed(() => this.page() === 0);
  protected readonly isLast = computed(() => this.page() >= this.totalPages() - 1);
}
