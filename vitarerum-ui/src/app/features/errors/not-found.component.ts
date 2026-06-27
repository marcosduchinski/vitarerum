import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterLink, LogoMarkComponent],
  templateUrl: './not-found.component.html',
  styleUrl: './not-found.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NotFoundComponent {}
