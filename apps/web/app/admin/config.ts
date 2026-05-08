const DEFAULT_DAGSTER_ADMIN_URL = "http://localhost:23000";

export function getDagsterAdminUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_TRIPMATE_DAGSTER_URL?.trim();
  return configuredUrl || DEFAULT_DAGSTER_ADMIN_URL;
}
