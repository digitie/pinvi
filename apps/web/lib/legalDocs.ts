// 법무 문서 웹 렌더 콘텐츠 (T-269). 작업 정본 초안은 docs/legal/*.md이며, 변호사 확정본이
// 나오면 그 기준으로 본 파일을 일괄 교체한다(초안 단계에서는 함께 갱신). 동의 UX(settings/
// consents, profile-complete)가 CONSENT_LEGAL_SLUG로 /legal/<slug>를 링크한다.
import type { ConsentType } from '@pinvi/schemas';

export interface LegalSection {
  heading: string;
  paragraphs: string[];
}

export interface LegalDoc {
  slug: string;
  title: string;
  /** 변호사 검토 전 초안 표시 */
  draft: boolean;
  version: string;
  /** 시행일 — 미정이면 null */
  effectiveDate: string | null;
  summary: string;
  sections: LegalSection[];
}

const TERMS: LegalDoc = {
  slug: 'terms-of-service',
  title: 'Pinvi 이용약관',
  draft: true,
  version: 'draft-0.1',
  effectiveDate: null,
  summary: 'Pinvi 서비스 이용과 관련한 회사·이용자의 권리·의무를 규정합니다.',
  sections: [
    {
      heading: '제1조 (목적)',
      paragraphs: [
        '본 약관은 Pinvi(이하 "회사")가 제공하는 한국 여행 계획·기록·공유 서비스의 이용과 관련하여 회사와 이용자의 권리·의무 및 책임사항을 규정합니다.',
      ],
    },
    {
      heading: '제2조 (서비스의 제공 및 변경)',
      paragraphs: [
        '서비스는 연중무휴 제공을 원칙으로 하되 점검·장애 등으로 중단될 수 있습니다.',
        '서비스는 대한민국 거주자/대한민국 IP 전용으로 제공되며 국외 접속은 제한될 수 있습니다.',
        '지도·날씨·이벤트 등 정보는 공공데이터/외부 API에 기반하며 정확성을 보증하지 않습니다.',
      ],
    },
    {
      heading: '제3조 (이용자의 의무)',
      paragraphs: [
        '타인 정보 도용·허위 등록, 제3자 권리 침해, 운영 방해, 법령·공서양속 위반 콘텐츠 게시를 하여서는 안 됩니다.',
      ],
    },
    {
      heading: '제4조 (콘텐츠의 권리와 관리)',
      paragraphs: [
        '이용자가 작성한 콘텐츠의 권리는 이용자에게 있으며, 회사는 서비스 제공·개선·백업 범위에서 이를 저장·표시할 수 있습니다.',
        '신고된 콘텐츠는 신고·검토·게시중단 절차에 따라 처리될 수 있습니다.',
      ],
    },
    {
      heading: '제5조 (해지 및 면책)',
      paragraphs: [
        '이용자는 언제든지 회원 탈퇴를 신청할 수 있습니다.',
        '회사는 천재지변, 외부 API 장애, 이용자 귀책 등 통제를 벗어난 사유로 인한 손해에 책임을 지지 않습니다.',
      ],
    },
  ],
};

const PRIVACY: LegalDoc = {
  slug: 'privacy-policy',
  title: 'Pinvi 개인정보 처리방침',
  draft: true,
  version: 'draft-0.1',
  effectiveDate: null,
  summary: '회사가 처리하는 개인정보의 항목·목적·보유기간과 이용자 권리를 안내합니다.',
  sections: [
    {
      heading: '1. 수집 항목',
      paragraphs: [
        '필수: 이메일, 비밀번호(Argon2 해시), 닉네임.',
        '자동 수집: 접속 IP, 기기/브라우저 정보, 이용 기록(보안·부정이용 방지).',
        '위치정보·인구통계·마케팅 수신은 별도 동의 시에만 처리합니다.',
      ],
    },
    {
      heading: '2. 이용 목적',
      paragraphs: [
        '회원 식별·인증, 서비스 제공·운영, 부정이용 방지, 법령상 의무 이행, (동의 시) 개선·마케팅.',
      ],
    },
    {
      heading: '3. 보유 기간',
      paragraphs: [
        '회원정보는 탈퇴 시까지 보유 후 지체 없이 파기합니다(법령상 의무 보존분 제외).',
        '위치정보 이용·제공사실 확인자료는 위치정보법 제16조에 따라 6개월 이상 보관합니다.',
      ],
    },
    {
      heading: '4. 정보주체의 권리 (DSR)',
      paragraphs: [
        '열람·정정·삭제·처리정지를 설정 > DSR 또는 support@pinvi.kr로 요청할 수 있으며, 10일 이내 처리·통지합니다.',
      ],
    },
    {
      heading: '5. 안전성 확보 조치',
      paragraphs: [
        '접근권한 관리(RBAC), 비밀번호 해시, 전송 암호화(TLS), 접속기록 보관·감사, 한국 전용 접근 제한을 적용합니다.',
      ],
    },
  ],
};

const LBS: LegalDoc = {
  slug: 'lbs-terms',
  title: 'Pinvi 위치기반서비스 이용약관',
  draft: true,
  version: 'draft-0.1',
  effectiveDate: null,
  summary: '위치정보법에 따른 위치기반서비스 이용 조건을 규정합니다.',
  sections: [
    {
      heading: '제1조 (목적·서비스 내용)',
      paragraphs: [
        '회사는 이용자의 개인위치정보를 이용하여 주변 장소·여행지 검색, 위치 기반 일정 작성 보조 등을 제공합니다.',
      ],
    },
    {
      heading: '제2조 (개인위치정보의 이용·제공)',
      paragraphs: [
        '회사는 이용자가 별도로 동의한 경우에 한하여 개인위치정보를 이용하며, 제3자에게 제공하지 않습니다.',
        '이용자는 동의의 전부/일부, 이용·제공의 일시 중지를 언제든 요구할 수 있고 회사는 거부하지 않습니다(설정 > 동의 관리에서 철회).',
      ],
    },
    {
      heading: '제3조 (이용·제공사실 확인자료의 보유)',
      paragraphs: [
        '회사는 위치정보법 제16조에 따라 이용·제공사실 확인자료를 자동 기록하고 6개월 이상 보관하며, 이용자는 열람을 요구할 수 있습니다.',
      ],
    },
    {
      heading: '제4조 (손해배상·분쟁조정)',
      paragraphs: [
        '회사가 위치정보법을 위반하여 손해가 발생한 경우 배상 책임을 집니다.',
        '위치정보 관련 분쟁은 방송통신위원회 재정 또는 개인정보분쟁조정위원회 조정을 신청할 수 있습니다.',
      ],
    },
  ],
};

const LOCATION: LegalDoc = {
  slug: 'location-consent',
  title: '개인위치정보 수집·이용 동의',
  draft: true,
  version: 'draft-0.1',
  effectiveDate: null,
  summary: '위치정보법에 따른 별도 동의 항목입니다. 거부 시 위치 기능만 제한됩니다.',
  sections: [
    {
      heading: '1. 수집·이용 목적',
      paragraphs: ['현재 위치 기반 주변 여행지·장소 검색·추천, 위치 기반 여행 일정 작성 보조.'],
    },
    {
      heading: '2. 수집 항목',
      paragraphs: [
        'GPS/Wi-Fi 등에 기반한 단말 위치(좌표). 기능 사용 시점에만 조회하며 상시 추적하지 않습니다.',
      ],
    },
    {
      heading: '3. 보유·이용 기간',
      paragraphs: [
        '기능 제공에 필요한 범위에서 일시 처리하며, 이용·제공사실 확인자료는 6개월 이상 보관됩니다.',
      ],
    },
    {
      heading: '4. 동의 거부 권리 및 철회',
      paragraphs: [
        '동의를 거부할 권리가 있으며 거부·철회 시 위치 기반 기능만 비활성화됩니다(위치정보법 제16조).',
        '설정 > 동의 관리에서 언제든 철회할 수 있고, 철회 즉시 이후 위치 수집이 중단됩니다.',
      ],
    },
  ],
};

export const LEGAL_DOCS: Record<string, LegalDoc> = {
  [TERMS.slug]: TERMS,
  [PRIVACY.slug]: PRIVACY,
  [LBS.slug]: LBS,
  [LOCATION.slug]: LOCATION,
};

export const LEGAL_SLUGS = Object.keys(LEGAL_DOCS);

/** 동의 type → 법무 문서 slug (필수 4항목). 선택 항목은 처리방침에 포함되어 별도 문서 없음. */
export const CONSENT_LEGAL_SLUG: Partial<Record<ConsentType, string>> = {
  tos: TERMS.slug,
  privacy: PRIVACY.slug,
  lbs_tos: LBS.slug,
  location_collection: LOCATION.slug,
};

export function getLegalDoc(slug: string): LegalDoc | undefined {
  return LEGAL_DOCS[slug];
}
