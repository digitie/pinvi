'use client';
import { PopoverContent as CommonContent } from '@kor-travel/ui/popover';
import type { ComponentProps } from 'react';
export {
  Popover,
  PopoverAnchor,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@kor-travel/ui/popover';
export function PopoverContent(props: ComponentProps<typeof CommonContent>) {
  return <CommonContent {...props} data-pv-surface="admin" />;
}
