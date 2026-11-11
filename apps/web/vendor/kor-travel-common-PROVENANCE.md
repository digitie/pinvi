# 공통 산출물 출처 및 무결성

현재 프런트엔드 후보는 integration-9-review이며 정식 registry 릴리스가 아니다. 부모가 만든 단일 tgz를 그대로 전달받아 사용한다. 같은 후보 버전의 bytes 변경은 승인된 통합 검증에 한하며 소비자가 자체 pack을 만들지 않는다.

| 패키지             | 버전                   | 라이선스(실제 package.json) |
| ------------------ | ---------------------- | --------------------------- |
| @kor-travel/tokens | 0.1.1                  | GPL-3.0-or-later            |
| @kor-travel/ui     | 0.2.0                  | GPL-3.0-or-later            |
| lightningcss       | 1.33.0+nativecss.fix.4 | MPL-2.0                     |
| vworld-map-core    | 1.0.1                  | GPL-3.0-only                |
| vworld-map-rn      | 1.0.1                  | GPL-3.0-only                |
| vworld-map-web     | 1.0.3                  | GPL-3.0-only                |

## 소스 정본

- common: 2c1182e765bb2bc53e01e0962cf2a73683891e1d
- maplibre-vworld-react: 9a7a348b02d61969b394c681b024d5851eef836b
- lightningcss: 748651cbd845971e65c411166ddee101745dab21
- serde-content: 18e53fcf6f8ace093a292891b34fa3411192617d

정확한 SHA512·파일명·상대 file 참조는 [앱 원장](../common-artifacts.json), root lock과 각 workspace 원장이 함께 고정한다. 현재 CSSfix4 파일은 15,376,394 bytes다. root의 $lightningcss/$vworld-map-core override와 각 앱 직접 file 의존성이 같은 물리 vendor 파일을 사용한다. LICENSE/NOTICE/소스 고지는 전달 archive 그대로 보존한다.

## 갱신과 검증

새 후보를 받을 때 부모 원장의 SHA512를 검증하여 동일 파일을 복사한다. UI/tokens는 apps/web에서 npm12.0.1의 명시적 file install로 lock과 실제 modules를 함께 갱신하고, apps/mobile의 공유 tokens file 경로도 명시적으로 재설치한다. lock만 편집하거나 integrity 값을 수동으로 바꾸지 않는다. CSS/core override 대상을 갱신할 때는 root의 apps/web/vendor 상대 경로에서 명시적으로 설치해야 workspace 재해석 ENOENT를 피한다.

설치 뒤 common guard·최신 외부 canonical guard와 실제 archive 전체 파일 비교를 수행한다. 기존 후보와 runtime/CSS/metadata가 같다는 파일별 증명이 있을 때 checker만의 변경으로 전체 앱 build/export를 재반복하지 않는다. 실행 증거와 한계는 [통합 보고서](../../../docs/reports/common-unification-20261111.md)에 기록한다.

이전 dev.9/tokens0.1.0 및 Base UI 후보의 파일·해시는 Git 이력에 보존되어 있다. 현재 작업 트리에는 manifest가 사용하는 tgz만 둔다.
