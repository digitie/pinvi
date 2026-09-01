'use client';

import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { fieldLabelClassName } from '@/components/admin/ui/field-variants';
import { Separator } from '@/components/admin/ui/separator';
import { cn } from '@/lib/admin/cn';

/**
 * KTM `src/components/ui/field.tsx`에서 이식(T-356).
 *
 * Field primitives — 폼 라벨/보조문/오류의 단일 recipe(M43). 모든 라벨 처리(FormField/FormSelect/
 * FormTextArea/직접 조합)는 여기서만 스타일을 얻는다.
 *
 * - `FieldLabel`/`FieldTitle`: 13.5px 500 ink-2, 컨트롤 위 6px(`gap-1.5`) — placeholder-as-label 금지.
 * - `FieldDescription`(hint) · `FieldError`: 라벨과 같은 크기, hint는 ink-2 · error는 danger.
 * - `FieldMessage`: hint/error가 번갈아 들어가는 **한 슬롯**(`min-h-[1lh]`) — 오류가 나타나도 폼이
 *   밀리지 않는다(M13). error가 있으면 hint를 대체한다.
 * - `Field[data-invalid]`는 라벨을 danger로, `[data-disabled]`는 라벨을 opacity 55로.
 *
 * ── 원문에서 바꾼 것 ──
 * 1. 색 토큰만 pinvi admin 이름으로 치환(`text-text-primary`→`text-ink`,
 *    `text-text-secondary`→`text-body`, `border-border`→`border-admin-line`,
 *    `bg-surface-page`→`bg-admin-page`, `text-destructive`→`text-admin-danger`,
 *    `text-brand`→`text-primary`, `border-brand`→`border-primary`,
 *    `bg-brand-tint`→`bg-error-bg`). 간격/radius/타이포/`data-*` variant 문자열은 원문 그대로다.
 * 2. 컨테이너 쿼리 제거: `FieldGroup`의 `@container/field-group`과 `orientation="responsive"`의
 *    `@md/field-group:*` variant를 뺐다(이식 지침 — pinvi에 컨테이너 쿼리 전제를 두지 않는다).
 *    그 결과 `responsive`는 `vertical`과 동일하게 동작한다. prop은 호출부 호환을 위해 남긴다.
 * 3. KTM 커스텀 variant를 표준 Tailwind 임의 variant로: `has-data-checked:` →
 *    `has-data-[state=checked]:`, `group-has-data-horizontal/field:` →
 *    `group-has-data-[orientation=horizontal]/field:`.
 * 4. `React.ComponentProps` 타입만 쓰던 원문에 `import * as React`를 추가했다(UMD 전역 의존 제거).
 * 5. `uniqueErrors?.length == 1` → `=== 1`(eslint eqeqeq. 동작 동일).
 *
 * `FieldSeparator`가 쓰는 `<Separator>`는 pinvi admin 이식본(`./separator`, base-ui 없이 네이티브
 * `role="separator"`)을 그대로 쓴다 — 호출 형태는 원문과 같다.
 */
function FieldSet({ className, ...props }: React.ComponentProps<'fieldset'>) {
  return (
    <fieldset
      data-slot="field-set"
      className={cn(
        'flex flex-col gap-4 has-[>[data-slot=checkbox-group]]:gap-3 has-[>[data-slot=radio-group]]:gap-3',
        className,
      )}
      {...props}
    />
  );
}

function FieldLegend({
  className,
  variant = 'legend',
  ...props
}: React.ComponentProps<'legend'> & { variant?: 'legend' | 'label' }) {
  return (
    <legend
      data-slot="field-legend"
      data-variant={variant}
      className={cn(
        'mb-1.5 font-medium text-ink data-[variant=label]:text-xs data-[variant=label]:text-body data-[variant=legend]:text-sm data-[variant=legend]:font-semibold',
        className,
      )}
      {...props}
    />
  );
}

function FieldGroup({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="field-group"
      className={cn(
        'group/field-group flex w-full flex-col gap-5 data-[slot=checkbox-group]:gap-3 *:data-[slot=field-group]:gap-4',
        className,
      )}
      {...props}
    />
  );
}

const fieldVariants = cva('group/field flex w-full gap-1.5', {
  variants: {
    orientation: {
      vertical: 'flex-col *:w-full [&>.sr-only]:w-auto',
      horizontal:
        'flex-row items-center gap-2 has-[>[data-slot=field-content]]:items-start *:data-[slot=field-label]:flex-auto has-[>[data-slot=field-content]]:[&>[role=checkbox],[role=radio]]:mt-px',
      // 컨테이너 쿼리(`@md/field-group:*`) 제거 → 남은 문자열이 vertical과 같다(위 주석 2).
      responsive: 'flex-col *:w-full [&>.sr-only]:w-auto',
    },
  },
  defaultVariants: {
    orientation: 'vertical',
  },
});

function Field({
  className,
  orientation = 'vertical',
  ...props
}: React.ComponentProps<'div'> & VariantProps<typeof fieldVariants>) {
  return (
    <div
      role="group"
      data-slot="field"
      data-orientation={orientation}
      className={cn(fieldVariants({ orientation }), className)}
      {...props}
    />
  );
}

function FieldContent({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="field-content"
      className={cn('group/field-content flex flex-1 flex-col gap-1 leading-snug', className)}
      {...props}
    />
  );
}

function FieldLabel({
  className,
  htmlFor,
  ...props
}: React.ComponentProps<'label'> & { htmlFor: string }) {
  return (
    <label
      data-slot="field-label"
      htmlFor={htmlFor}
      className={cn(
        'group/field-label peer/field-label flex w-fit items-center gap-1.5',
        fieldLabelClassName,
        // 라벨이 Field(체크박스 카드 등)를 감싸는 경우: hairline 1층 + 선택 시 brand-tint(불투명)
        'has-[>[data-slot=field]]:w-full has-[>[data-slot=field]]:flex-col has-[>[data-slot=field]]:rounded-control has-[>[data-slot=field]]:border has-[>[data-slot=field]]:border-admin-line has-[>[data-slot=field]]:text-ink *:data-[slot=field]:p-2.5 has-[>[data-slot=field]]:has-data-[state=checked]:border-primary has-[>[data-slot=field]]:has-data-[state=checked]:bg-error-bg',
        className,
      )}
      {...props}
    />
  );
}

function FieldTitle({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="field-label"
      className={cn('flex w-fit items-center gap-1.5', fieldLabelClassName, className)}
      {...props}
    />
  );
}

function FieldDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return (
    <p
      data-slot="field-description"
      className={cn(
        'text-left text-xs leading-normal font-normal text-body group-has-data-[orientation=horizontal]/field:text-balance [[data-variant=legend]+&]:-mt-1.5',
        '[&>a]:text-primary [&>a]:underline-offset-4 [&>a:hover]:underline',
        className,
      )}
      {...props}
    />
  );
}

/**
 * hint/error 공용 메시지 슬롯. 항상 1줄 높이를 예약해(`min-h-[1lh]`) 오류 등장/소멸이 레이아웃을
 * 밀지 않게 한다. 자식이 없으면 빈 슬롯으로 남는다.
 */
function FieldMessage({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="field-message"
      className={cn('min-h-[1lh] text-xs leading-normal', className)}
      {...props}
    />
  );
}

function FieldSeparator({
  children,
  className,
  ...props
}: React.ComponentProps<'div'> & {
  children?: React.ReactNode;
}) {
  return (
    <div
      data-slot="field-separator"
      data-content={!!children}
      className={cn(
        'relative -my-2 h-5 text-xs group-data-[variant=outline]/field-group:-mb-2',
        className,
      )}
      {...props}
    >
      <Separator className="absolute inset-0 top-1/2" />
      {children && (
        <span
          className="relative mx-auto block w-fit bg-admin-page px-2 text-body"
          data-slot="field-separator-content"
        >
          {children}
        </span>
      )}
    </div>
  );
}

function FieldError({
  className,
  children,
  errors,
  ...props
}: React.ComponentProps<'div'> & {
  errors?: Array<{ message?: string } | undefined>;
}) {
  let content: React.ReactNode = children;

  if (!content) {
    if (!errors?.length) {
      return null;
    }

    const uniqueErrors = [...new Map(errors.map((error) => [error?.message, error])).values()];

    if (uniqueErrors?.length === 1) {
      content = uniqueErrors[0]?.message;
    } else {
      content = (
        <ul className="ml-4 flex list-disc flex-col gap-1">
          {uniqueErrors.map(
            (error) => error?.message && <li key={error.message}>{error.message}</li>,
          )}
        </ul>
      );
    }
  }

  if (!content) {
    return null;
  }

  return (
    <div
      role="alert"
      data-slot="field-error"
      className={cn('text-xs leading-normal font-normal text-admin-danger', className)}
      {...props}
    >
      {content}
    </div>
  );
}

export {
  Field,
  FieldLabel,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLegend,
  FieldMessage,
  FieldSeparator,
  FieldSet,
  FieldContent,
  FieldTitle,
};
