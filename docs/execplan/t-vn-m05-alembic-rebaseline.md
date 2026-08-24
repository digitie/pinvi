# T-VN-M05 Alembic rebaseline 실행 계획

## 상태

active graph·rebaseline proof·M05 owner 전환과 단일 N150 target lease의 구현 회귀를 완료했다.
새 PostgreSQL 16 role topology, root-only legacy `0061` profile, migration 뒤 migrator login 봉인까지
검증했다. N150 paired live browser E2E·최종 적대 리뷰·PR CI·병합이 남았다. ADR-065의 구현 정본이다.

## 목표

긴 Pinvi Alembic 이력을 active graph에서 제거하고, 새 설치는 `20260824_0100` 기준선과
`20260824_0101` 현재 main·M05 통합 revision만 적용하게 한다. N150 운영 DB의 실제 사용자·감사 데이터는
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
3. `0101`이 N150 `0061` 뒤 current main에 합류한 location-audit·동의 이력 변경과 M05의
   충돌했던 옛 `0062`·`0063`·`0064` 계약을 하나로 적용하게 한다.
4. root-only rebaseline helper가 `0061` catalog fingerprint와 fresh backup proof를 확인한 뒤
   version row만 `0100`으로 바꾸게 한다.
5. 이전 기준선의 fresh bootstrap과 `0061 → 0100 → 0101` rehearsal, M05 recovery/preflight를
   통과했다. 최신 main 통합본으로 같은 검증을 다시 실행하고 N150 browser E2E와 최종 적대 리뷰를
   남긴다.
6. fresh install은 root bootstrap이 extension·non-login app schema owner·non-login migration
   owner·one-shot migrator login을 만들고, `0101` 안에서 M05 부분만 `SET LOCAL ROLE`로 owner를
   전환한다. 기존 N150 `0061`은 object owner를 재작성하지 않고 승인된 root-only legacy profile로
   같은 M05 전환만 수행한다.

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
4. fresh DB에서는 `app-migrator` one-shot으로 `0101`을 적용하고 role/receipt owner/`NOLOGIN`·`CONNECT`
   revoke·기존 migrator session 종료 seal,
   M05 ACL, API DB health를 확인한다. 현재 N150 `0061`은 이 단계 직전에만 root-only
   `PINVI_M05_LEGACY_REBASELINE=1` + 별도 root URL profile과 root-owned `0600` applied rebaseline
   receipt를 명시한다. `0101`이 receipt의 `0061` preflight DB identity와 현재 `0100` handoff row를
   대조한 뒤, 기존 app DDL 뒤 M05 object만 migration owner로 전환됐는지 확인한다.
5. 실패 시 새 history를 억지로 stamp하지 않고 snapshot 복구 후 fail-closed 원인을 해결한다.

## 완료 기준

- fresh DB가 `0100 → 0101`로 bootstrap되고 app catalog fingerprint가 기준값과 일치한다.
- disposable `0061` DB가 data row 보존 상태로 rebaseline 후 `0101`까지 올라간다.
- helper는 unknown revision, data-less/dirty catalog, M05 object 존재, backup proof 누락을 모두 거부한다.
- fresh role topology와 root-only legacy profile 모두 M05 receipt owner를 runtime/fence/database owner와
  분리하고, 성공·실패 후 one-shot migrator login을 `NOLOGIN`·`CONNECT` revoke·session 0으로 봉인한다.
- M05 focused PostgreSQL 검증·N150 browser E2E·두 전문 적대 리뷰가 통과한다.
- production 전환은 merge 뒤 별도 승인 gate로 남고 M05 activation은 `false`다.
