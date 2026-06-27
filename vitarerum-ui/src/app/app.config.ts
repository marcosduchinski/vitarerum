import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { definePreset } from '@primeuix/themes';
import Aura from '@primeuix/themes/aura';
import {
  API_BASE_URL,
  TURNSTILE_SITE_KEY,
  USE_MOCK_API,
  USE_MOCK_AUTH,
} from '@core/config/app-config.model';
import { AppConfigService } from '@core/config/app-config.service';
import { authInterceptor } from '@core/auth/auth.interceptor';
import { sessionExpiredInterceptor } from '@core/auth/session-expired.interceptor';
import { provideProposalChat } from '@core/providers/provide-proposal-chat';
import { provideCollectionUse } from '@core/providers/provide-collection-use';
import { provideIdentity } from '@core/providers/provide-identity';
import { provideUserManagement } from '@core/providers/provide-user-management';
import { providePrimeNG } from 'primeng/config';

import { routes } from './app.routes';

const VitarerumPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#edf0fb',
      100: '#dae1f7',
      200: '#b5c3ef',
      300: '#8da3e6',
      400: '#5c75da',
      500: '#2c4bce',
      600: '#1f3aab',
      700: '#1a308e',
      800: '#142470',
      900: '#0e1a52',
      950: '#080f33',
    },
    colorScheme: {
      light: {
        primary: {
          color: '{primary.500}',
          contrastColor: '#ffffff',
          hoverColor: '{primary.600}',
          activeColor: '{primary.700}',
        },
      },
    },
  },
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor, sessionExpiredInterceptor])),
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: VitarerumPreset,
        options: {
          darkModeSelector: '.app-dark',
        },
      },
    }),
    provideAppInitializer(() => inject(AppConfigService).load()),
    {
      provide: API_BASE_URL,
      useFactory: (config: AppConfigService) => config.get('api-base-url'),
      deps: [AppConfigService],
    },
    {
      provide: USE_MOCK_API,
      useFactory: (config: AppConfigService) => config.get('use-mock-api'),
      deps: [AppConfigService],
    },
    {
      provide: USE_MOCK_AUTH,
      // Falls back to use-mock-api when the key is absent, preserving older config files.
      useFactory: (config: AppConfigService) =>
        config.get('use-mock-auth') ?? config.get('use-mock-api'),
      deps: [AppConfigService],
    },
    {
      provide: TURNSTILE_SITE_KEY,
      // Empty string when unset: the public page treats that as "no captcha configured".
      useFactory: (config: AppConfigService) => config.get('turnstile-site-key') ?? '',
      deps: [AppConfigService],
    },
    provideIdentity(),
    provideCollectionUse(),
    provideProposalChat(),
    provideUserManagement(),
  ],
};
