'use client';
import { TooltipContent as CommonContent } from '@kor-travel/ui/tooltip';
import type { ComponentProps } from 'react';
export { Tooltip, TooltipProvider, TooltipTrigger } from '@kor-travel/ui/tooltip';
export function TooltipContent(props: ComponentProps<typeof CommonContent>) {
  return <CommonContent {...props} data-pv-surface="admin" />;
}
