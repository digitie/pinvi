'use client';
// kor-travel-map admin `src/components/multi-filter-combobox.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
// - 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM `design.md` 전용 표식이다.
// - import 경로: `@/components/ui/input` → `@/components/admin/ui/input`,
//   `@/lib/string-list` → `@/lib/admin/string-list`(이번에 함께 이식), `@/lib/utils` →
//   `@/lib/admin/cn`.
// - 문자열 따옴표를 pinvi prettier 설정(`singleQuote: true`)에 맞춰 작은따옴표로 바꿨다.
// - 색 토큰 치환표만 적용(레이아웃/간격/높이/모션/포커스 클래스는 원문 그대로):
//   `text-text-primary`→`text-ink`, `text-text-secondary`→`text-body`,
//   `bg-surface-subtle`→`bg-admin-subtle`, `bg-surface-muted`→`bg-admin-muted`,
//   `border-input`→`border-admin-control-line`, `border-border`→`border-admin-line`,
//   `bg-card`→`bg-canvas`, `shadow-elevated`→`shadow-card`.
//   `rounded-control`/`rounded-panel`/`h-control-sm`/`min-h-control`/`text-2xs`/`duration-fast`는
//   pinvi에 같은 이름·같은 값으로 있어 그대로 쓴다. `outline-focus`도 이름이 같다.
// - `z-20`은 원문 그대로 뒀다. pinvi DESIGN.md의 named z-index 규칙(`z-nav` 이상)은 페이지 스택
//   레이어를 위한 것이고, 여기 팝업은 **필드 컨테이너 내부**의 로컬 stacking이라 named 티어에
//   올리면 오히려 상위 패널/모달 위로 튀어나온다. admin 표면은 그 lint 규칙의 대상 밖이다.
// - **base-ui는 쓰지 않는다** — 원문도 안 쓴다. 팝업은 원문과 동일하게 `absolute` 자체 배치이고
//   dismiss는 컨테이너 `onBlur`(포커스 밖으로 나가면 닫기) + Escape 키다. 이식 과정에서
//   포지셔닝/dismiss 로직을 새로 만들지 않았다.
// - 그 외 로직·키보드 규약(`aria-activedescendant`, ↑/↓/Home/End/Enter/Escape/Backspace)·
//   접근성 이름 규약·한국어 문구는 한 글자도 바꾸지 않았다.
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { XIcon } from 'lucide-react';

import { Input } from '@/components/admin/ui/input';
import { cn } from '@/lib/admin/cn';
import { uniqueSorted } from '@/lib/admin/string-list';

interface MultiFilterComboboxProps {
  ariaLabel: string;
  className?: string;
  onChange: (values: string[]) => void;
  options: string[];
  placeholder: string;
  values: string[];
}

/**
 * 팝업 항목 레시피 — 30px row, hover paper-2, 활성 항목(aria-selected)은 paper-2, pressed rules 색.
 * 항목은 포커스를 받지 않는다(포커스는 입력에 머무르고 `aria-activedescendant`가 활성 항목을
 * 가리킨다 — WAI-ARIA combobox 규약), 그래서 focus-visible 레시피가 아니라 aria-selected 레시피다.
 */
const optionRowClass =
  'flex h-control-sm w-full cursor-pointer items-center rounded-control px-2 text-left text-xs text-ink transition-[color,background-color] duration-fast ease-out hover:bg-admin-subtle aria-selected:bg-admin-subtle active:bg-admin-muted';

type ComboboxItem = {
  /** 화면에 보이는 문구(신규 추가 항목은 `추가: …`). */
  label: string;
  /** 선택 시 실제로 더해지는 값. */
  value: string;
  key: string;
};

/**
 * 다중 선택 필터 콤보박스 — 선택값은 chip(hairline, 배지 아님 — M22), 입력은 chip 옆 인라인,
 * 컨테이너가 focus 를 대신 표시(`:has(input:focus-visible)`), 팝업은 `shadow-card` 한 층.
 *
 * 키보드: ↑/↓·Home/End 로 활성 항목 이동(`aria-activedescendant`), Enter 로 활성 항목(없으면 입력한
 * 문자열) 추가, Escape 로 팝업 닫기, Backspace(빈 입력) 로 마지막 chip 제거. chip 을 ✕ 로 지우면
 * 사라진 버튼 대신 입력으로 포커스가 돌아온다.
 */
function MultiFilterCombobox({
  ariaLabel,
  className,
  onChange,
  options,
  placeholder,
  values,
}: MultiFilterComboboxProps) {
  const baseId = useId();
  const listId = `${baseId}-listbox`;
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [query, setQuery] = useState('');
  const [popupOpen, setPopupOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const normalizedQuery = query.trim().toLowerCase();
  const selected = useMemo(() => uniqueSorted(values), [values]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const selectableOptions = useMemo(
    () =>
      uniqueSorted([...options, ...selected]).filter(
        (option) =>
          !selectedSet.has(option) &&
          (normalizedQuery.length === 0 || option.toLowerCase().includes(normalizedQuery)),
      ),
    [normalizedQuery, options, selected, selectedSet],
  );

  const items = useMemo<ComboboxItem[]>(() => {
    const trimmed = query.trim();
    const creatable =
      trimmed.length > 0 && !selectedSet.has(trimmed) && !selectableOptions.includes(trimmed);
    return [
      ...(creatable ? [{ key: `add:${trimmed}`, label: `추가: ${trimmed}`, value: trimmed }] : []),
      ...selectableOptions
        .slice(0, 12)
        .map((option) => ({ key: `option:${option}`, label: option, value: option })),
    ];
  }, [query, selectableOptions, selectedSet]);

  const activeItem =
    activeIndex >= 0 && activeIndex < items.length ? items[activeIndex] : undefined;
  const activeDescendant = popupOpen && activeItem ? `${baseId}-option-${activeIndex}` : undefined;

  useEffect(() => {
    if (!popupOpen || activeIndex < 0) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, popupOpen]);

  const addValue = useCallback(
    (value: string) => {
      const next = value.trim();
      if (!next || selectedSet.has(next)) return;
      onChange(uniqueSorted([...selected, next]));
      setQuery('');
      setActiveIndex(-1);
      setPopupOpen(false);
    },
    [onChange, selected, selectedSet],
  );

  const removeValue = useCallback(
    (value: string) => {
      onChange(selected.filter((item) => item !== value));
    },
    [onChange, selected],
  );

  const moveActive = (nextIndex: number) => {
    if (items.length === 0) {
      setActiveIndex(-1);
      return;
    }
    const clamped = Math.min(Math.max(nextIndex, 0), items.length - 1);
    setActiveIndex(clamped);
  };

  return (
    <div
      className={cn('relative flex min-w-0 flex-col gap-1', className)}
      onBlur={(event) => {
        const nextFocus = event.relatedTarget;
        if (!nextFocus || !event.currentTarget.contains(nextFocus as Node)) {
          setPopupOpen(false);
          setActiveIndex(-1);
        }
      }}
      onFocus={() => setPopupOpen(true)}
    >
      <div className="flex min-h-control flex-wrap items-center gap-1 rounded-control border border-admin-control-line bg-canvas px-2 py-0.5 transition-[border-color,background-color] duration-fast ease-out has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-focus">
        {selected.map((value) => (
          <span
            className="inline-flex h-6 max-w-full items-center gap-0.5 rounded-control border border-admin-line bg-admin-subtle pl-2 pr-0.5 text-2xs text-ink"
            key={value}
          >
            <span className="max-w-36 truncate">{value}</span>
            <button
              aria-label={`${value} 제거`}
              className="relative inline-flex size-5 shrink-0 items-center justify-center rounded-control text-body transition-[color,background-color] duration-fast ease-out before:absolute before:-inset-1 hover:bg-admin-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus active:bg-admin-muted"
              type="button"
              onClick={() => {
                removeValue(value);
                // 지운 버튼과 함께 포커스가 사라지면 body로 떨어진다 — 필드로 되돌린다.
                inputRef.current?.focus();
              }}
            >
              <XIcon aria-hidden="true" className="size-3" />
            </button>
          </span>
        ))}
        <Input
          aria-activedescendant={activeDescendant}
          aria-autocomplete="list"
          aria-controls={popupOpen && items.length > 0 ? listId : undefined}
          aria-expanded={popupOpen}
          aria-label={ariaLabel}
          /* 포커스 링은 컨테이너가 대신 그린다(`has-[input:focus-visible]`). 안쪽 입력의 링은
             `outline-hidden`(= outline-style 파괴)이 아니라 폭 0으로 끈다 — twMerge 가 같은 그룹의
             `focus-visible:outline-2`를 이 값으로 대체하므로 CSS 순서에 기대지 않는다(P1-1). */
          className="min-w-28 flex-1 border-0 bg-transparent px-1 shadow-none data-[size=sm]:px-1 hover:bg-transparent focus-visible:border-transparent focus-visible:bg-transparent focus-visible:outline-0"
          placeholder={selected.length === 0 ? placeholder : '추가'}
          ref={inputRef}
          role="combobox"
          size="sm"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
            setPopupOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setPopupOpen(true);
              moveActive(activeIndex < 0 ? 0 : activeIndex + 1);
              return;
            }
            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setPopupOpen(true);
              moveActive(activeIndex < 0 ? items.length - 1 : activeIndex - 1);
              return;
            }
            if (event.key === 'Home' && popupOpen && items.length > 0) {
              event.preventDefault();
              moveActive(0);
              return;
            }
            if (event.key === 'End' && popupOpen && items.length > 0) {
              event.preventDefault();
              moveActive(items.length - 1);
              return;
            }
            if (event.key === 'Escape') {
              if (!popupOpen) return;
              // 팝업을 우리가 닫았으면 바깥(dialog 등)까지 Escape가 번지지 않게 한다.
              event.preventDefault();
              event.stopPropagation();
              setPopupOpen(false);
              setActiveIndex(-1);
              return;
            }
            if (event.key === 'Enter') {
              event.preventDefault();
              addValue(activeItem ? activeItem.value : query);
              return;
            }
            if (event.key === 'Backspace' && query.length === 0 && selected.length > 0) {
              removeValue(selected[selected.length - 1] ?? '');
            }
          }}
        />
      </div>
      {/* 팝업은 필드가 포커스를 가지는 동안 열려 있고, 비어 있으면 "선택지가 없습니다."를 보여 준다.
          예전에는 그 조건에서 팝업 자체가 닫혀 있어 이 문구에 도달할 수 없었다(P2-8).
          listbox 에는 접근성 이름을 주지 않는다 — ARIA 1.2 combobox 패턴에서 팝업은 입력의
          `aria-controls`/`aria-activedescendant` 로 연결되고 이름은 입력이 소유한다. 팝업에
          `aria-label` 을 얹으면 필드 이름이 DOM 에 두 번 나타나, `getByLabel("dedup provider")`
          같은 e2e 계약이 입력과 listbox 둘 다에 걸려 strict mode 위반이 된다(부분 일치라
          `"… 후보 목록"` 처럼 접미사를 붙여도 마찬가지다). */}
      {popupOpen ? (
        <div className="absolute top-full right-0 left-0 z-20 mt-1 max-h-56 overflow-auto rounded-panel border border-admin-line bg-canvas p-1 shadow-card">
          {items.length > 0 ? (
            <div id={listId} ref={listRef} role="listbox">
              {items.map((item, index) => (
                <div
                  aria-selected={index === activeIndex}
                  className={optionRowClass}
                  data-index={index}
                  id={`${baseId}-option-${index}`}
                  key={item.key}
                  role="option"
                  onClick={() => addValue(item.value)}
                  // 항목을 눌러도 포커스는 입력에 머문다 — 팝업이 blur로 닫히지 않게.
                  onMouseDown={(event) => event.preventDefault()}
                >
                  {item.label}
                </div>
              ))}
            </div>
          ) : (
            <p className="px-2 py-1.5 text-xs text-body">선택지가 없습니다.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export { MultiFilterCombobox };
