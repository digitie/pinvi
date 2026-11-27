import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import {
  groupAccessibility,
  hasAccessibilityBadge,
  hasPetBadge,
  petPolicyLines,
  sourceAttributionLine,
  visitGuideRows,
  withDisplayKeys,
  type VisitGuideOmittable,
} from '@pinvi/domain';
import type { VisitGuide as VisitGuideData } from '@pinvi/schemas';

type Panel = 'accessibility' | 'pet';

/** 배지 겸 펼침 버튼 — 색만으로 뜻을 전하지 않도록 글자와 펼침 표시(▾/▴)를 함께 둔다. */
function BadgeToggle({
  label,
  expanded,
  onToggle,
  testID,
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
  testID: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ expanded }}
      onPress={onToggle}
      className={`min-h-11 justify-center rounded-sm border px-3 ${
        expanded ? 'border-ink bg-ink' : 'border-hairline bg-canvas'
      }`}
      testID={testID}
    >
      <Text className={`text-xs font-semibold ${expanded ? 'text-canvas' : 'text-ink'}`}>
        {label}
        <Text accessible={false} importantForAccessibility="no">
          {expanded ? ' ▴' : ' ▾'}
        </Text>
      </Text>
    </Pressable>
  );
}

/**
 * 이용 안내(Map visitor_info): 원천 문장 그대로의 이용시간·휴무·요금·주차 등 + 무장애·반려동물 배지(눌러
 * 펼침) + 출처(+ 기준일). 문장은 텍스트로만 그린다(RN Text는 줄바꿈을 그대로 보인다).
 */
export function VisitGuide({
  guide,
  omit,
}: {
  guide: VisitGuideData;
  /** 같은 시트의 영업 정보 항목이 이미 보이는 줄(이용시간·휴무) — 겹치지 않게 뺀다. */
  omit?: readonly VisitGuideOmittable[];
}) {
  const [open, setOpen] = useState<Panel | null>(null);
  const rows = visitGuideRows(guide, { omit });
  const accessibility = hasAccessibilityBadge(guide) ? groupAccessibility(guide.accessibility) : [];
  const pet = hasPetBadge(guide) ? petPolicyLines(guide) : [];
  if (rows.length === 0 && accessibility.length === 0 && pet.length === 0) return null;
  const toggle = (panel: Panel) => setOpen((current) => (current === panel ? null : panel));
  return (
    <View className="gap-2" testID="place-sheet-visit-guide">
      {rows.map((row) => (
        <View key={row.key} className="gap-0.5" testID={`place-sheet-visit-guide-${row.key}`}>
          <Text className="text-xs font-semibold text-muted">{row.label}</Text>
          {withDisplayKeys(row.lines, (line) => line).map(({ item: line, key }) => (
            <Text key={key} className="text-sm text-body">
              {line}
            </Text>
          ))}
        </View>
      ))}
      {accessibility.length > 0 || pet.length > 0 ? (
        <View className="flex-row flex-wrap gap-2">
          {accessibility.length > 0 ? (
            <BadgeToggle
              label="무장애 안내"
              expanded={open === 'accessibility'}
              onToggle={() => toggle('accessibility')}
              testID="place-sheet-visit-guide-accessibility-toggle"
            />
          ) : null}
          {pet.length > 0 ? (
            <BadgeToggle
              label="반려동물 동반"
              expanded={open === 'pet'}
              onToggle={() => toggle('pet')}
              testID="place-sheet-visit-guide-pet-toggle"
            />
          ) : null}
        </View>
      ) : null}
      {open === 'accessibility' && accessibility.length > 0 ? (
        <View className="gap-2" testID="place-sheet-visit-guide-accessibility">
          {accessibility.map((view) => (
            <View key={view.group} className="gap-0.5">
              <Text accessibilityRole="header" className="text-xs font-semibold text-muted">
                {view.label}
              </Text>
              {withDisplayKeys(view.items, (note) => `${note.facility}|${note.text}`).map(
                ({ item, key }) => (
                  <Text key={key} className="text-sm text-body">
                    {item.label}: {item.text}
                  </Text>
                ),
              )}
            </View>
          ))}
        </View>
      ) : null}
      {open === 'pet' && pet.length > 0 ? (
        <View className="gap-2" testID="place-sheet-visit-guide-pet">
          {pet.map((line) => (
            <View key={line.key} className="gap-0.5">
              <Text className="text-xs font-semibold text-muted">{line.label}</Text>
              <Text className="text-sm text-body">{line.text}</Text>
            </View>
          ))}
        </View>
      ) : null}
      <Text className="text-xs text-muted" testID="place-sheet-visit-guide-attribution">
        {sourceAttributionLine(guide)}
      </Text>
    </View>
  );
}
