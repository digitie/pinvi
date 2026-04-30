const DEFAULT_API_BASE_URL = "http://localhost:8001";

export function getApiBaseUrlCandidates(): string[] {
  const primary = process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? DEFAULT_API_BASE_URL;
  return [primary];
}

export async function fetchApi(path: string, init: RequestInit = {}): Promise<Response> {
  const candidates = getApiBaseUrlCandidates();
  let firstNetworkError: unknown = null;

  for (const [index, baseUrl] of candidates.entries()) {
    try {
      return await fetch(`${baseUrl}${path}`, init);
    } catch (error) {
      firstNetworkError ??= error;
      if (index === candidates.length - 1) {
        throw error;
      }
    }
  }

  throw firstNetworkError instanceof Error
    ? firstNetworkError
    : new Error("API 서버에 연결하지 못했다.");
}
