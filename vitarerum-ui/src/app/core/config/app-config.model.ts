import { InjectionToken } from '@angular/core';

export interface AppConfig {
  'app-name': string;
  'app-version': string;
  'api-base-url': string;
  'use-mock-api': boolean;
  'use-mock-auth'?: boolean;
  // Cloudflare Turnstile site key for the public proposal submission page.
  // This is a PUBLIC key (safe to ship in the bundle); the secret key lives
  // only on the server, which verifies the token via siteverify.
  'turnstile-site-key'?: string;
}

export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL');
export const USE_MOCK_API = new InjectionToken<boolean>('USE_MOCK_API');
export const USE_MOCK_AUTH = new InjectionToken<boolean>('USE_MOCK_AUTH');
export const TURNSTILE_SITE_KEY = new InjectionToken<string>('TURNSTILE_SITE_KEY');
