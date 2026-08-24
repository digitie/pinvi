# T-VN-M05 Alembic rebaseline 실행 계획

## 상태

구현·로컬 리허설 완료, 최종 검증·리뷰·PR 병합 진행 중. ADR-062의 구현 정본이다.

## 목표

긴 Pinvi Alembic 이력을 active graph에서 제거하고, 새 설치는 `20260824_0100` 기준선과
`20260824_0101` M05 통합 revision만 적용하게 한다. N150 운영 DB의 실제 사용자·감사 데이터는
삭제하지 않고, 검증된 `20260821_0061 → 20260824_0100 → 20260824_0101` 전환만 허용한다.

## 확인된 운영 사실

- N150 운영 DB: PostgreSQL 16, `app.alembic_version=20260821_0061`.
- `app` regular table 61개와 실제 행이 있어 데이터 보존이 필요하다.
- M05 `ops.m05_activation_database_anchor`와
  `ops.m05_hotswap_release_receipts`는 아직 없다.
- API mount만으로 backup artifact는 확인할 수 없었다. production 전환 전에는 root-only
  producer로 새 snapshot을 만들고 checksum을 검증해야 한다.

## 범위

1. active `apps/api/alembic/versions/`를 `0100`/`0101` 두 revision으로 재구성한다.
2. `0100`이 fresh PostgreSQL 16 catalog에서 `0061`의 Pinvi-owned schema를 재현하게 한다.
3. `0101`이 M05 `0062`·`0063`·`0064` 계약을 하나로 적용하게 한다.
4. root-only rebaseline helper가 `0061` catalog fingerprint와 fresh backup proof를 확인한 뒤
   version row만 `0100`으로 바꾸게 한다.
5. fresh bootstrap과 `0061 → 0100 → 0101` rehearsal, M05 recovery/preflight를 통과했다.
   N150 browser E2E와 최종 적대 리뷰를 남겼다.

## 비범위

- 운영 DB에서 이 계획을 지금 실행하거나 M05 activation을 켜지 않는다.
- 과거 revision DB의 범용 compatibility layer를 만들지 않는다.
- `feature`/`provider_sync` schema와 kor-travel-map Alembic graph를 바꾸지 않는다.

## 구현 순서

1. clean PostgreSQL 16에서 기존 `0061` catalog의 deterministic schema fingerprint와
   `0100` baseline SQL을 생성한다. user data, role password, host 정보, `alembic_version` row는
   포함하지 않는다.
2. `0100` revision과 fresh bootstrap integration test를 추가한다.
3. `0062`·`0063`·`0064`를 `0101`로 합치고, 모든 final-boundary revision pin을 `0101`로
   바꾼다.
4. rebaseline helper에 exact source revision, fingerprint, backup checksum manifest, one-row
   version update 및 rollback-on-error를 구현한다.
5. old revision 파일과 과거 revision-specific regression을 active path에서 제거하고,
   새 두 단계에 맞는 tests/docs를 갱신한다.

## 운영 전환 gate

1. root-only producer로 fresh app snapshot과 checksum을 만든다.
2. N150에서 helper의 read-only preflight가 `0061`·fingerprint·M05 object absence·backup proof를
   모두 통과하는지 확인한다.
3. 별도 운영 변경 승인 뒤 helper의 `--confirm`을 한 번 실행한다.
4. `alembic upgrade 20260824_0101`을 적용하고 revision, M05 ACL, API DB health를 확인한다.
5. 실패 시 새 history를 억지로 stamp하지 않고 snapshot 복구 후 fail-closed 원인을 해결한다.

## 완료 기준

- fresh DB가 `0100 → 0101`로 bootstrap되고 app catalog fingerprint가 기준값과 일치한다. (통과)
- disposable `0061` DB가 data row 보존 상태로 rebaseline 후 `0101`까지 올라간다. (통과)
- helper는 unknown revision, data-less/dirty catalog, M05 object 존재, backup proof 누락을 모두 거부한다.
- M05 focused PostgreSQL 검증·N150 browser E2E·두 전문 적대 리뷰가 통과한다.
- production 전환은 merge 뒤 별도 승인 gate로 남고 M05 activation은 `false`다.
