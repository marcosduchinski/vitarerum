import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import { computed, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { fromEvent, startWith, Subject } from 'rxjs';

interface LayoutState {
  staticMenuDesktopInactive: boolean;
  staticMenuMobileActive: boolean;
}

const DESKTOP_BREAKPOINT = 991;

@Injectable({ providedIn: 'root' })
export class LayoutService {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly state = signal<LayoutState>({
    staticMenuDesktopInactive: false,
    staticMenuMobileActive: false,
  });

  readonly layoutState = this.state.asReadonly();
  readonly isDarkTheme = signal(false);

  private readonly overlayOpenSubject = new Subject<void>();
  readonly overlayOpen$ = this.overlayOpenSubject.asObservable();

  /**
   * A signal that emits whenever the window resizes (browser only).
   * It is used solely to invalidate the `isDesktop` computed signal.
   */
  private readonly _resizeTick = isPlatformBrowser(this.platformId)
    ? toSignal(fromEvent(this.document.defaultView!, 'resize').pipe(startWith(null)), {
        initialValue: null,
      })
    : signal(null);

  /** Reactive desktop breakpoint signal — updates on window resize. Always `true` in SSR. */
  readonly isDesktop = computed(() => {
    this._resizeTick(); // subscribe so resize events invalidate this computed
    if (!isPlatformBrowser(this.platformId)) return true;
    return (this.document.defaultView?.innerWidth ?? DESKTOP_BREAKPOINT + 1) > DESKTOP_BREAKPOINT;
  });


  readonly isSidebarVisible = computed(
    () =>
      (this.isDesktop() && !this.state().staticMenuDesktopInactive) ||
      this.state().staticMenuMobileActive,
  );

  onMenuToggle(): void {
    if (this.isDesktop()) {
      this.state.update((s) => ({
        ...s,
        staticMenuDesktopInactive: !s.staticMenuDesktopInactive,
      }));
    } else {
      this.state.update((s) => ({
        ...s,
        staticMenuMobileActive: !s.staticMenuMobileActive,
      }));
      this.overlayOpenSubject.next();
    }
  }

  closeMenu(): void {
    this.state.update((s) => ({
      ...s,
      staticMenuMobileActive: false,
    }));
  }

  toggleDarkMode(): void {
    const next = !this.isDarkTheme();
    this.isDarkTheme.set(next);
    if (!isPlatformBrowser(this.platformId)) return;
    this.document.documentElement.classList.toggle('app-dark', next);
  }
}

