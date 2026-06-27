import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

import { AppFooterComponent } from '@layout/footer/app-footer.component';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

/**
 * Minimal chrome for the public (unauthenticated) pages: brand mark + footer,
 * no sidebar, topbar, or role selector. Hosts the public routes via outlet.
 */
@Component({
  selector: 'app-public-shell',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, AppFooterComponent, LogoMarkComponent],
  templateUrl: './public-shell.component.html',
  styleUrl: './public-shell.component.scss',
})
export class PublicShellComponent {}
