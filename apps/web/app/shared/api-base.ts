const DEFAULT_API_BASE_URL = "http://localhost:8001";
const AUTH_REFRESH_EXCLUDED_PATHS = new Set([
  "/auth/login",
  "/auth/logout",
  "/auth/refresh",
  "/auth/register",
  "/auth/verify-email",
  "/admin/auth/login",
  "/admin/auth/logout",
  "/admin/auth/refresh",
]);

export function getApiBaseUrlCandidates(): string[] {
  const primary = process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? DEFAULT_API_BASE_URL;
  return [primary];
}

export async function fetchApi(path: string, init: RequestInit = {}): Promise<Response> {
  const requestInit = {
    ...init,
    credentials: init.credentials ?? "include",
  } satisfies RequestInit;

  const response = await fetchWithCandidates(path, requestInit);
  if (response.status !== 401 || AUTH_REFRESH_EXCLUDED_PATHS.has(stripQuery(path))) {
    return response;
  }

  const refreshPath = path.startsWith("/admin") ? "/admin/auth/refresh" : "/auth/refresh";
  const refreshResponse = await fetchWithCandidates(refreshPath, {
    method: "POST",
    credentials: "include",
  });
  if (!refreshResponse.ok) {
    return response;
  }

  return fetchWithCandidates(path, requestInit);
}

async function fetchWithCandidates(path: string, init: RequestInit): Promise<Response> {
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

function stripQuery(path: string): string {
  return path.split("?", 1)[0] ?? path;
}
