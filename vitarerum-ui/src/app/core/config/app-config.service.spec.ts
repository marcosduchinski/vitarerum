import { AppConfigService } from './app-config.service';

describe('AppConfigService', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('throws when a config value is read before loading', () => {
    const service = new AppConfigService();

    expect(() => service.get('api-base-url')).toThrow(
      '[AppConfig] "api-base-url" accessed before initialization',
    );
  });

  it('loads runtime config through fetch', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        return new Response(
          JSON.stringify({
            'app-name': 'Vitarerum',
            'app-version': '0.0.0',
            'api-base-url': 'http://localhost:4200/vitarerum-api',
            'use-mock-api': true,
          }),
        );
      }),
    );

    const service = new AppConfigService();

    await service.load();

    expect(fetch).toHaveBeenCalledWith('/config/environment.json');
    expect(service.get('api-base-url')).toBe('http://localhost:4200/vitarerum-api');
    expect(service.get('use-mock-api')).toBe(true);
  });
});
