'use client';

import { RouteError } from '@/components/feedback/RouteError';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError error={error} reset={reset} scope="root" testId="root-error-page" />;
}
