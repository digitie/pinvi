# 공통 산출물 채택 출처

고정 catalog/policy C는 main 병합 P(2b0c02a2018c2c8c791bc6d6c7b5a2290579e09e)의 선행 commit이다. 실제 R/P pack bytes 동일성이 확인됐다. 운영 적용은 별도다.

pack 생성 SOURCE_SHA: 706aaa7821588dfca72f660c9161f56be2d0445f
고정 catalog commit: 5c1b3857e9af060d30ec776157760fb9e9c13ded
정책 commit: 5c1b3857e9af060d30ec776157760fb9e9c13ded
main 발행 근거: https://github.com/digitie/kor-travel-common/actions/runs/44313659808/artifacts/14430019630
producer: 706aaa7821588dfca72f660c9161f56be2d0445f

- @kor-travel/tokens 0.1.3 sha512-m1WsuJw1DHYxAkPsJpAIrFN5P/Udb+Ln/sZHbrmPJpItQDHx+wuf8QEFgSrBsk5yW+NAX5CQnIQZRkPIFwO97A==
- @kor-travel/ui 0.2.2 sha512-/odxLZlFlMj0IB8oPMyjE77kj1MtZO46m/lyHiCTW/gYFq7o6XUSrSPOC7rm7cyEpbjD8dAnCqcz7zmE2GWF+Q==

기존 직접 의존성만 갱신한다. Pinvi 모바일은 tokens-only를 유지한다.
lock은 Node26/npm12 재생성과 정본 guard 대조 후 수용한다.

## 과거 출처 기록 — 이전 현재 버전 설명

# 공통 산출물 출처 및 무결성

현재 정본은 integration-12-review다(2026-11-17, common #58 동결: ui 0.2.1·tokens 0.1.2·vworld web 1.0.4/rn 1.0.2). 부모가 동결한 tgz·원장을 그대로 소비한다.
common PR49는 main e8ed3ae75000be5cd22a3a11492bd97660635d78로 병합됐다.
동일 버전의 bytes를 바꾸거나 독립 pack을 만들지 않는다. 후속 runtime 변경은 새 버전으로 소비한다.
원장의 제작 시점 status 라벨은 정본 그대로 보존한다.

| 패키지 | 정확 버전 | 실제 package.json 라이선스 | SHA512 |
| --- | --- | --- | --- |
| @kor-travel/tokens | 0.1.2 | GPL-3.0-or-later | sha512-IF5qTyPe0LrVFvHRHp2roruudcOO2U96b11zVr0D+Ir1Twsuc2UcAqkYoEL6LfMpDMiq6Xp+CfIDv7N/zkmo/w== |
| @kor-travel/ui | 0.2.1 | GPL-3.0-or-later | sha512-Yk0TFRE3UUPhHH3ErzgYQtNft+pzy3J5oYZaLwc4MnhUVUT3KPlvCQJDZtj8MvbKdNcVmi4fduxx3Z0FcIfTnw== |
| lightningcss | 1.33.0+nativecss.fix.4 | MPL-2.0 | sha512-zDQ03VJE37OlyBrLsRcsEdIVu0T4BXJKDH5y9//To6GlGN2UrKQGERFVAFblkPQ5ZEbhuOp5wpXxGARZNdbQLA== |
| vworld-map-core | 1.0.1 | GPL-3.0-only | sha512-Djm14Arr7U0r7Sabj6P0V57CdzWIGaJmecklmY1hwrq1QUZJjMUFgkZfGRFalUo6AFzHEwwzOEzbJPMifGhINw== |
| vworld-map-rn | 1.0.2 | GPL-3.0-only | sha512-ZJ6WmcABs8Jia6VZUOKutSYBPaWp7Ws/9wEMEcHwrVlpUwiBysCYOmvaUDtBj2HaSN3CgUMjzRQW2KlJs4yElQ== |
| vworld-map-web | 1.0.4 | GPL-3.0-only | sha512-yuie33P42nb6pHoR+rI3OTNzXmW/HdIbh6RCEWEooaVTg2lNax8NkakTiadZR/Osw34a6IO0jRxANaE16g6mKA== |
| @radix-ui/react-focus-scope | 1.3.1+kortravel.fix.2 | MIT | sha512-v3XweXrUSZ/QfrMVvYmsAkVNDnvcN21QKbSrViXYf0OQf5Ue9xSgqQIukgGjsYMEBQ5qxQW8fnOC9t1Y0ENPXw== |

## 소스 정본

- common: 938d1db701286414113324da714132db62e3311e (ui 0.2.1·tokens 0.1.2 producer, main push docs `packages` artifact `common-release-packs-938d1db…`)
- maplibre-vworld-react: 79b70997de8dd4a6bcc9630233f14f273cb27991 (web 1.0.4 — #33 vworld:// 스킴 수정, rn 1.0.2 — #34 web 대조 수정. 세 tgz 모두 이 commit의 main push Marker CI pack이며 core 1.0.1·web 1.0.4는 이전 pack과 byte 동일)
- lightningcss: 748651cbd845971e65c411166ddee101745dab21
- serde-content: 18e53fcf6f8ace093a292891b34fa3411192617d
- radix-ui-primitives: 1752a539c8d5ae57961a0fa2702d2573d48fefe7

중앙 reusable code/common-ref는 55a921b55d248106cbe320e7f5305f3d3cdb60fe를 유지한다.
producer a35481349d6747b4f13b958ae64d9c0bbd0b5413과 검사 코드 pin을 구분한다.

Scope fix.2는 source1752a539c8d5ae57961a0fa2702d2573d48fefe7의 33,511bytes이며
SHA256은 1ca04870692565c243130d99c3dba91f3ac853ab2ec9538fc7b658b17fb7b49a다.
root/web의 공식 runtime file 의존성과 root $@radix-ui/react-focus-scope override가 물리 사본1개를 고정한다.
mobile에는 직접 DOM Scope 의존성을 넣지 않는다.

root/web/mobile 원장의 source·7종 version/SRI는 같으며 file 경로만 각 workspace 기준으로 다르다.
정확한 파일명은 [웹 원장](../common-artifacts.json), root lock과 각 workspace 원장이 함께 고정한다.
LICENSE/NOTICE/실제 소스 고지는 전달 archive 그대로 보존한다. CSSfix4와 지도3종 bytes는 바뀌지 않았다.

## 갱신과 검증

동명 UI/tokens는 npm12.0.1의 명시적 file 설치로 lock·actual modules를 갱신한다.
Scope는 root의 apps/web/vendor 상대 경로에서 명시적으로 설치해 workspace 중복 경로 ENOENT를 피한다.
웹 UI/tokens·모바일 tokens도 각 workspace의 file 경로로 명시 재설치하고 root install로 정규화한다.
lock integrity를 수동 편집하거나 legacy-peer/force를 사용하지 않는다.
종료된 본인 QA 설치에서 확인된 UI/tokens/Scope 폴더만 정리하며 공유 cache는 삭제하지 않는다.

actual7종297파일(UI94/tokens25/Scope15 포함)을 archive 원문과 byte 비교한다.
원장·lock·실제 버전/사본과 installed/external canonical 웹·모바일 guard를 함께 확인한다.
C10→C11은 UI/tokens의 policy JSON2개만 변경됐고 나머지117파일은 동일하다.
Scope runtime은 바뀌었으므로 최종 웹 build·전체 단위/브라우저와 모달 초기 포커스·fieldset 경계를 새로 검증한다.
기존 native fix4의4 export·글꼴·모바일 웹 증거는 native 소스 및 tokens runtime 동일성 근거로 보존한다.
그 결과를 새 웹 runtime 수용으로 대신하지 않는다.

최종 결과·실패 이력·원문 로그·미실행 범위는 [통합 보고서](../../../docs/reports/common-unification-20261111.md)를 따른다.
기존 C9 520/1·207/2/4와 C10 521/0·207/2/4는 해당 입력의 별도 기록으로 유지한다.
현재 작업 트리에는 manifest가 사용하는 tgz만 두고 이전 후보는 Git 이력에 보존한다.
