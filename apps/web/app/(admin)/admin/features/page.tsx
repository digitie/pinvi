import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminFeaturesPage() {
  return (
    <Placeholder
      title="라이브러리 (feature)"
      sprint={5}
      description="python-krtour-map.feature schema read-only — Record Linkage + sources/overrides/weather."
      notes={[
        'GET /admin/features (search, kind 필터)',
        'GET /admin/features/{id}/sources',
        'GET /admin/features/{id}/overrides',
        'GET /admin/features/{id}/weather-values',
        'admin은 직접 INSERT 금지 (라이브러리 위임)',
      ]}
    />
  );
}
