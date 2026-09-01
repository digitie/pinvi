import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { FormField } from '@/components/admin/ui/form-field-input';
import { FormSelect } from '@/components/admin/ui/form-select';
import { FormTextArea } from '@/components/admin/ui/form-textarea';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';

/**
 * KTM `src/components/ui/form-field-input.test.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 것:
 * 1. import를 상대경로에서 pinvi alias(`@/components/admin/ui/*`)로.
 * 2. 파일 상단 `// @vitest-environment jsdom` 제거 — pinvi vitest는 이미 jsdom 단일 환경이다.
 * 케이스와 단언은 원문 그대로다.
 */
afterEach(() => cleanup());

/**
 * required 필드는 라벨에 장식용 별표(`<span aria-hidden> *</span>`)를 붙이는데, Chromium
 * accname이 그 별표를 접근성 이름에 포함시켜 `"name *"`가 되어 `getByLabel(name,{exact})`가
 * 미스됐다(KTM 라이브 e2e 적색). 컨트롤에 명시 aria-label을 부여해 접근성 이름을 별표 없는
 * 라벨로 고정한다. 본 테스트는 그 aria-label 배선을 결정적으로 가드한다.
 */
describe('required field accessible name (aria-label override)', () => {
  it('FormField(required) gives the input a clean aria-label = label', () => {
    render(<FormField label="name" required value="" onChange={() => {}} />);
    const input = screen.getByRole('textbox');
    expect(input.getAttribute('aria-label')).toBe('name');
    expect(input.getAttribute('aria-required')).toBe('true');
  });

  it('FormField(non-required) sets no aria-label (label alone names it)', () => {
    render(<FormField label="memo" value="" onChange={() => {}} />);
    expect(screen.getByRole('textbox').getAttribute('aria-label')).toBeNull();
  });

  it('caller-provided aria-label overrides the required default', () => {
    render(<FormField label="name" required aria-label="이름" value="" onChange={() => {}} />);
    expect(screen.getByRole('textbox').getAttribute('aria-label')).toBe('이름');
  });

  it('FormSelect(required) gives the select a clean aria-label = label', () => {
    render(
      <FormSelect label="kind" required value="place" onChange={() => {}}>
        <NativeSelectOption value="place">place</NativeSelectOption>
      </FormSelect>,
    );
    expect(screen.getByRole('combobox').getAttribute('aria-label')).toBe('kind');
  });

  it('FormTextArea(required) gives the textarea a clean aria-label = label', () => {
    render(<FormTextArea label="reason" required value="" onChange={() => {}} />);
    expect(screen.getByRole('textbox').getAttribute('aria-label')).toBe('reason');
  });
});
