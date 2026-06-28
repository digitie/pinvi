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

/**
 * Conflict resolution applies the user's chosen "mine" values for the fields shown in the
 * dialog, but the dialog's field list is hardcoded and can drift from what the editor
 * actually emits. Any patch field NOT offered for a server-vs-mine choice must still be
 * carried through (keep mine), otherwise that edit is silently dropped on a version
 * conflict (T-290). Returns the keys to apply: selected "mine" keys ∪ undisplayed patch
 * keys, restricted to keys actually present in the patch.
 */
export function resolveConflictKeys(
  patchKeys: readonly string[],
  displayedKeys: readonly string[],
  selectedMineKeys: readonly string[],
): string[] {
  const patchKeySet = new Set(patchKeys);
  const displayed = new Set(displayedKeys);
  const result = new Set<string>();
  for (const key of selectedMineKeys) {
    if (patchKeySet.has(key)) result.add(key);
  }
  for (const key of patchKeys) {
    // Not offered for a choice in the dialog → keep the user's value rather than drop it.
    if (!displayed.has(key)) result.add(key);
  }
  return Array.from(result);
}
