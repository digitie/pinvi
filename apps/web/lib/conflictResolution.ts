export function pickConflictPatch<T extends object, K extends Extract<keyof T, string>>(
  patch: T,
  selectedKeys: readonly K[],
): Partial<T> {
  const next: Partial<T> = {};
  for (const key of selectedKeys) {
    if (Object.prototype.hasOwnProperty.call(patch, key)) {
      next[key] = patch[key];
    }
  }
  return next;
}

export function hasPatchFields(patch: object): boolean {
  return Object.keys(patch).length > 0;
}
