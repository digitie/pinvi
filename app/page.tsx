const sampleStops = [
  {
    time: "09:30",
    title: "Neighborhood breakfast",
    meta: "Seongsu · 45 min · ₩18,000",
  },
  {
    time: "11:00",
    title: "Gallery and design shops",
    meta: "Walkable cluster · 2.1 km",
  },
  {
    time: "15:30",
    title: "Han River sunset route",
    meta: "Bike or taxi · weather check",
  },
];

export default function Home() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="hero-title">
        <div className="heroText">
          <p className="eyebrow">TripMate</p>
          <h1 id="hero-title">여행 아이디어를 바로 일정으로.</h1>
          <p className="lede">
            장소, 예산, 동행자 의견, 이동 시간을 한 화면에서 맞춰보는 여행 계획
            워크스페이스입니다.
          </p>
          <div className="actions">
            <a href="#planner" className="primaryAction">
              새 여행 만들기
            </a>
            <a href="#brief" className="secondaryAction">
              제품 방향 보기
            </a>
          </div>
        </div>
        <div className="routePreview" aria-label="Sample itinerary preview">
          <div className="routeHeader">
            <span>Seoul weekend</span>
            <strong>Day 2</strong>
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

      <section className="workspace" id="planner" aria-label="Trip planning modules">
        <div>
          <p className="sectionLabel">Planning surface</p>
          <h2>처음부터 지도보다 결정이 먼저 보이게.</h2>
        </div>
        <div className="modules">
          <article>
            <span>01</span>
            <h3>Itinerary</h3>
            <p>날짜별 동선, 머무는 시간, 예약 상태를 함께 정리합니다.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Saved places</h3>
            <p>가고 싶은 곳을 후보로 모으고 거리와 우선순위를 비교합니다.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Companions</h3>
            <p>동행자의 취향, 제약, 투표를 일정 결정에 반영합니다.</p>
          </article>
        </div>
      </section>

      <section className="brief" id="brief">
        <p className="sectionLabel">Next build target</p>
        <h2>다음 단계는 실제 여행 생성 플로우입니다.</h2>
        <p>
          Trip, ItineraryDay, Place 모델을 먼저 세우고 샘플 데이터를 실제 편집
          가능한 화면으로 바꾸는 것이 첫 번째 제품 슬라이스입니다.
        </p>
      </section>
    </main>
  );
}
