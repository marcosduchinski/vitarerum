import { Injectable } from '@angular/core';

import { AppConfig } from './app-config.model';

@Injectable({ providedIn: 'root' })
export class AppConfigService {
  private config: AppConfig | null = null;

  async load(): Promise<void> {
    let response: Response;
    try {
      response = await fetch('/config/environment.json');
    } catch {
      throw new Error('[AppConfig] Network error: could not reach configuration endpoint');
    }
    if (!response.ok) {
      throw new Error(
        `[AppConfig] Failed to load configuration: HTTP ${response.status} ${response.statusText}`,
      );
    }
    this.config = (await response.json()) as AppConfig;
  }

  get<K extends keyof AppConfig>(key: K): AppConfig[K] {
    if (this.config === null) {
      throw new Error(`[AppConfig] "${String(key)}" accessed before initialization`);
    }

    return this.config[key];
  }
}
