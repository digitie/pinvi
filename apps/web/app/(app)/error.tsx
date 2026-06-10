'use client';

import { RouteError } from '@/components/feedback/RouteError';

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError error={error} reset={reset} scope="app" testId="app-error-page" />;
}
