import { describe, expect, it } from 'vitest';
import { MOCKED_SERVICE_ENV, mockedAppURL } from '../e2e/mocked-origins';

describe('mocked application environment', () => {
  it('defaults to the isolated test port and fixed reserved upstreams', () => {
    expect(mockedAppURL().origin).toBe('http://127.0.0.1:13805');
    expect(new URL(MOCKED_SERVICE_ENV.NEXT_PUBLIC_PINVI_API_URL).hostname).toBe(
      'pinvi-api.e2e.invalid',
    );
    expect(new URL(MOCKED_SERVICE_ENV.PINVI_GRAFANA_HEALTH_URL).hostname).toBe(
      'pinvi-grafana.e2e.invalid',
    );
    expect(MOCKED_SERVICE_ENV.NEXT_PUBLIC_VWORLD_API_KEY).toBe('');
  });

  it.each(['http://127.0.0.1:13805', 'http://localhost:13905', 'http://[::1]:13805'])(
    'accepts isolated loopback %s',
    (url) => {
      expect(mockedAppURL(url).origin).toBe(url);
    },
  );

  it.each([
    'https://production.example',
    'http://127.0.0.1:12805',
    'http://localhost:12801',
    'http://127.0.0.1:12205',
    'http://127.0.0.1:12701',
    'http://127.0.0.1:14101',
    'http://127.0.0.1:13805/subpath',
    'http://user:secret@127.0.0.1:13805',
    'http://127.0.0.1:13805/?token=secret',
    'http://127.0.0.1:13805/#secret',
    'not-a-url-secret',
  ])('rejects live, service or secret-bearing configuration without echoing it', (url) => {
    expect(() => mockedAppURL(url)).toThrow('mocked suite requires an isolated local HTTP origin');
    try {
      mockedAppURL(url);
    } catch (error) {
      expect(String(error)).not.toContain('secret');
    }
  });
});
