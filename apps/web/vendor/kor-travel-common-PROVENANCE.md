# 공통 산출물 출처 및 무결성

현재 정본은 integration-11-review의 foundation 최초릴리스7종이다. 부모가 동결한 tgz·원장을 그대로 소비한다.
common PR49는 main e8ed3ae75000be5cd22a3a11492bd97660635d78로 병합됐다.
동일 버전의 bytes를 바꾸거나 독립 pack을 만들지 않는다. 후속 runtime 변경은 새 버전으로 소비한다.
원장의 제작 시점 status 라벨은 정본 그대로 보존한다.

| 패키지 | 정확 버전 | 실제 package.json 라이선스 | SHA512 |
| --- | --- | --- | --- |
| @kor-travel/tokens | 0.1.1 | GPL-3.0-or-later | sha512-85mqNJXqhTlA4RbtKUhmzx6rH6mOOeNmsXTJtCetQ5y8njLy+5XLZbdT6j1tf3ME9XQA6X63Ah4kmuLdqEZHbA== |
| @kor-travel/ui | 0.2.0 | GPL-3.0-or-later | sha512-BsRRdnJUp6FQ2KWkXtINb7IkrxxwnWFlLP/oVlNN4UXBKren7uTlnYT4iJsdaO98iA4Tn2EMPX06eT2uB5jEDA== |
| lightningcss | 1.33.0+nativecss.fix.4 | MPL-2.0 | sha512-zDQ03VJE37OlyBrLsRcsEdIVu0T4BXJKDH5y9//To6GlGN2UrKQGERFVAFblkPQ5ZEbhuOp5wpXxGARZNdbQLA== |
| vworld-map-core | 1.0.1 | GPL-3.0-only | sha512-Djm14Arr7U0r7Sabj6P0V57CdzWIGaJmecklmY1hwrq1QUZJjMUFgkZfGRFalUo6AFzHEwwzOEzbJPMifGhINw== |
| vworld-map-rn | 1.0.1 | GPL-3.0-only | sha512-lgDBasKIEG2ElQ9jnHDB9pA+x04Xge9yzBb1NPPw1auyvlkQvxsq4NfRPIrw1VWiutcGiIefySLiVaZDUkO69Q== |
| vworld-map-web | 1.0.3 | GPL-3.0-only | sha512-HPXZcz/wP6tFsCZqlAbansWNICcZPubC+/V7rDWXYTQVlOBLl9cZQ1HSMJd25c2CZoMNreVFTQA0vzkVglkS1w== |
| @radix-ui/react-focus-scope | 1.3.1+kortravel.fix.2 | MIT | sha512-v3XweXrUSZ/QfrMVvYmsAkVNDnvcN21QKbSrViXYf0OQf5Ue9xSgqQIukgGjsYMEBQ5qxQW8fnOC9t1Y0ENPXw== |

## 소스 정본

- common: a35481349d6747b4f13b958ae64d9c0bbd0b5413
- maplibre-vworld-react: 9a7a348b02d61969b394c681b024d5851eef836b
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
