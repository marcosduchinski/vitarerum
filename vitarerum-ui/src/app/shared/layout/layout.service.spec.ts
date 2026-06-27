import { DOCUMENT } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { LayoutService } from './layout.service';

describe('LayoutService', () => {
  afterEach(() => {
    document.documentElement.classList.remove('app-dark');
  });

  it('toggles dark mode on the injected document root', () => {
    TestBed.configureTestingModule({});
    const service = TestBed.inject(LayoutService);

    service.toggleDarkMode();

    expect(service.isDarkTheme()).toBe(true);
    expect(document.documentElement.classList.contains('app-dark')).toBe(true);

    service.toggleDarkMode();

    expect(service.isDarkTheme()).toBe(false);
    expect(document.documentElement.classList.contains('app-dark')).toBe(false);
  });

  it('uses a desktop fallback when running outside the browser', () => {
    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: DOCUMENT, useValue: document },
      ],
    });
    const service = TestBed.inject(LayoutService);

    expect(service.isDesktop()).toBe(true);
    expect(service.isSidebarVisible()).toBe(true);
  });

  it('does not mutate document classes when toggling dark mode outside the browser', () => {
    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: DOCUMENT, useValue: document },
      ],
    });
    const service = TestBed.inject(LayoutService);

    service.toggleDarkMode();

    expect(service.isDarkTheme()).toBe(true);
    expect(document.documentElement.classList.contains('app-dark')).toBe(false);
  });
});
