import Constants from 'expo-constants';

const DEFAULT_API_BASE_URL = 'http://localhost:12801';
const DEFAULT_VWORLD_TOKEN_PATH = '/mobile/vworld/token';

type PinviExtra = {
  apiBaseUrl?: string;
  vworld?: {
    keySource?: 'server-issued';
    tokenPath?: string;
    bundledApiKey?: false;
  };
};

const pinviExtra = Constants.expoConfig?.extra?.pinvi as PinviExtra | undefined;

const apiBaseUrl =
  process.env.EXPO_PUBLIC_PINVI_API_URL ?? pinviExtra?.apiBaseUrl ?? DEFAULT_API_BASE_URL;

export const mobileConfig = {
  apiBaseUrl,
  vworld: {
    keySource: 'server-issued',
    tokenPath: pinviExtra?.vworld?.tokenPath ?? DEFAULT_VWORLD_TOKEN_PATH,
    bundledApiKey: false,
  },
} as const;

export function getVWorldTokenUrl(): string {
  return new URL(mobileConfig.vworld.tokenPath, mobileConfig.apiBaseUrl).toString();
}
