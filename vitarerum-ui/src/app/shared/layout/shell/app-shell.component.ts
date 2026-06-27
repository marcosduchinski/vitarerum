import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  PLATFORM_ID,
  Renderer2,
} from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';

import { AppFooterComponent } from '@layout/footer/app-footer.component';
import { AppSidebarComponent } from '@layout/sidebar/app-sidebar.component';
import { AppTopbarComponent } from '@layout/topbar/app-topbar.component';
import { LayoutService } from '@layout/layout.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, AppTopbarComponent, AppSidebarComponent, AppFooterComponent],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppShellComponent {
  protected readonly layoutService = inject(LayoutService);
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly renderer = inject(Renderer2);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private menuOutsideClickListener?: () => void;
  private readonly overlayOpenSubscription = this.layoutService.overlayOpen$
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe(() => {
      if (!isPlatformBrowser(this.platformId)) return;
      this.menuOutsideClickListener ??= this.renderer.listen(
        'document',
        'click',
        (event: MouseEvent) => {
          if (this.isOutsideClicked(event)) this.hideMenu();
        },
      );
      this.renderer.addClass(this.document.body, 'blocked-scroll');
    });
  private readonly navigationEndSubscription = this.router.events
    .pipe(
      filter((e) => e instanceof NavigationEnd),
      takeUntilDestroyed(this.destroyRef),
    )
    .subscribe(() => this.hideMenu());

  protected readonly containerClass = computed(() => {
    const state = this.layoutService.layoutState();
    return {
      'layout-wrapper': true,
      'layout-static': true,
      'layout-static-inactive': state.staticMenuDesktopInactive,
      'layout-mobile-active': state.staticMenuMobileActive,
    };
  });

  private isOutsideClicked(event: MouseEvent): boolean {
    if (!isPlatformBrowser(this.platformId)) return false;
    const sidebar = this.document.querySelector('.layout-sidebar');
    const menuBtn = this.document.querySelector('.layout-menu-button');
    const target = event.target as Node;
    return !(
      sidebar?.isSameNode(target) ||
      sidebar?.contains(target) ||
      menuBtn?.isSameNode(target) ||
      menuBtn?.contains(target)
    );
  }

  private hideMenu(): void {
    this.layoutService.closeMenu();
    this.menuOutsideClickListener?.();
    this.menuOutsideClickListener = undefined;
    if (!isPlatformBrowser(this.platformId)) return;
    this.renderer.removeClass(this.document.body, 'blocked-scroll');
  }
}
