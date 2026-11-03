import AdminFeaturesClient from './AdminFeaturesClient';

type Search = Record<string, string | string[] | undefined>;

export default async function AdminFeaturesPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const rawId = typeof params.feature_id === 'string' ? params.feature_id : '';
  const validId =
    rawId.length <= 200 &&
    /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|f_[a-z0-9_]+)$/i.test(rawId);
  const initialFeatureId = validId ? rawId : undefined;
  const initialQuery =
    initialFeatureId ?? (typeof params.q === 'string' ? params.q.slice(0, 200) : '');
  return (
    <AdminFeaturesClient
      key={`${initialFeatureId ?? ''}:${initialQuery}`}
      initialFeatureId={initialFeatureId}
      initialQuery={initialQuery}
    />
  );
}
