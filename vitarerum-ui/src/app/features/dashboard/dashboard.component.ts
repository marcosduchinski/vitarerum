import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';

interface DashboardMetric {
  label: string;
  value: number;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  protected readonly metrics = signal<DashboardMetric[]>([
    { label: 'New proposals', value: 12 },
    { label: 'Active projects', value: 8 },
    { label: 'Pending reviews', value: 4 },
  ]);

  protected readonly totalOpenWork = computed(() =>
    this.metrics().reduce((total, metric) => total + metric.value, 0),
  );
}
