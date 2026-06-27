import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AppMenuComponent } from '@layout/menu/app-menu.component';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, AppMenuComponent, LogoMarkComponent],
  templateUrl: './app-sidebar.component.html',
  styleUrl: './app-sidebar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppSidebarComponent {}
