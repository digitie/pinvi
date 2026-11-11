'use client';
import { cn } from '@/lib/admin/cn';
import { Card as CommonCard } from '@kor-travel/ui/card';
import type { ComponentProps } from 'react';
export {
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@kor-travel/ui/card';
export function Card({ className, ...props }: ComponentProps<typeof CommonCard>) {
  return <CommonCard className={cn('group/card', className)} {...props} />;
}
