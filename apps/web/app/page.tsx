const sampleStops = [
  {
    time: "09:30",
    title: "성수동 아침 식사",
    meta: "서울 성동구 · 45분 · 약 8,000원",
  },
  {
    time: "11:00",
    title: "전시와 디자인 편집숍",
    meta: "도보 이동권 · 약 2.1km",
  },
  {
    time: "15:30",
    title: "한강 노을 동선",
    meta: "따릉이 또는 택시 · 날씨 확인",
  },
];

export default function Home() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="hero-title">
        <div className="heroText">
          <p className="eyebrow">TripMate</p>
          <h1 id="hero-title">국내 여행 계획을 지도와 일정으로 한 번에.</h1>
          <p className="lede">
            대한민국 여행에 맞춰 장소, 날짜, 알림, 지역 데이터를 함께 관리하는 여행 계획
            작업 공간입니다.
          </p>
          <div className="actions">
            <a href="#planner" className="primaryAction">
              여행 만들기
            </a>
            <a href="#brief" className="secondaryAction">
              제품 방향 보기
            </a>
          </div>
        </div>
        <div className="routePreview" aria-label="샘플 일정 미리보기">
          <div className="routeHeader">
            <span>서울 주말 여행</span>
            <strong>2일차</strong>
          </div>
          <ol>
            {sampleStops.map((stop) => (
              <li key={stop.time}>
                <time>{stop.time}</time>
                <div>
                  <strong>{stop.title}</strong>
                  <span>{stop.meta}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="workspace" id="planner" aria-label="여행 계획 모듈">
        <div>
          <p className="sectionLabel">Planning surface</p>
          <h2>지도, 일정, 알림을 같은 흐름에서 다룹니다.</h2>
        </div>
        <div className="modules">
          <article>
            <span>01</span>
            <h3>일정</h3>
            <p>날짜별 장소 순서, 이동 메모, 준비 상태를 한 화면에서 정리합니다.</p>
          </article>
          <article>
            <span>02</span>
            <h3>장소</h3>
            <p>검색 결과 선택과 지도 클릭으로 국내 여행 장소를 추가합니다.</p>
          </article>
          <article>
            <span>03</span>
            <h3>알림</h3>
            <p>여행별 Telegram 대상과 지역 기반 날씨·유가 요약을 관리합니다.</p>
          </article>
        </div>
      </section>

      <section className="brief" id="brief">
        <p className="sectionLabel">Next build target</p>
        <h2>다음 구현 단위는 로그인과 여행 생성 흐름입니다.</h2>
        <p>
          현재 화면은 구조 기준선입니다. 이후 Trip, TripDay, Place 모델을 API와
          연결하고 Kakao 지도 기반 장소 추가 흐름으로 확장합니다.
        </p>
      </section>
    </main>
  );
}
