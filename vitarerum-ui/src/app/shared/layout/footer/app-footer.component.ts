import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-footer',
  standalone: true,
  templateUrl: './app-footer.component.html',
  styleUrls: ['./app-footer.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppFooterComponent {
  protected readonly appName = 'Vitarerum';
  protected readonly appVersion = 'v1.0.0';
}
