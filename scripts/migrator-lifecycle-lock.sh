#!/usr/bin/env bash
# Shared host-local exclusion for the one-shot migrator credential lifecycle.
# Both deployment wrappers must hold this from writer drain through final seal:
# a second password rotation would otherwise terminate the first wrapper's
# migrator backend. Staging/production use a pre-created root-owned lock;
# disposable smoke stacks use a private per-user /tmp directory.

MIGRATOR_LIFECYCLE_LOCK_FD=""
MIGRATOR_LIFECYCLE_LOCK_PATH_ACTIVE=""

migrator_lifecycle_lock_path() {
  if [[ -n "${PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH:-}" ]]; then
    printf '%s\n' "$PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH"
    return
  fi
  case "${PINVI_ENVIRONMENT:-smoke}" in
    staging|production) printf '%s\n' "/var/lib/pinvi/restore-forensics/migrator-lifecycle.lock" ;;
    *) printf '/tmp/pinvi-migrator-lifecycle-%s/migrator-lifecycle.lock\n' "$(id -u)" ;;
  esac
}

_migrator_lifecycle_lock_path_is_safe() {
  local path="$1"
  [[ "$path" == /* && "$path" != *:* && "$path" != *$'\n'* ]] || {
    echo "PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH must be an absolute host path" >&2
    return 2
  }
}

_migrator_lifecycle_lock_prepare_file() {
  local path="$1"
  local parent owner mode parent_owner parent_mode
  parent="$(dirname -- "$path")"
  if [[ -z "${PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH:-}" \
    && "${PINVI_ENVIRONMENT:-smoke}" != "staging" \
    && "${PINVI_ENVIRONMENT:-smoke}" != "production" \
    && ! -e "$parent" && ! -L "$parent" ]]; then
    if ! (umask 077; mkdir -- "$parent"); then
      [[ -d "$parent" && ! -L "$parent" ]] || {
        echo "migrator lifecycle lock parent must be a regular directory" >&2
        return 2
      }
    fi
  fi
  [[ -d "$parent" && ! -L "$parent" ]] || {
    echo "migrator lifecycle lock parent must be a regular directory" >&2
    return 2
  }

  case "${PINVI_ENVIRONMENT:-smoke}" in
    staging|production)
      [[ "$(id -u)" == "0" ]] || {
        echo "staging/production migrator lifecycle lock requires root execution" >&2
        return 2
      }
      [[ -f "$path" && ! -L "$path" ]] || {
        echo "staging/production migrator lifecycle lock must be a pre-created regular file" >&2
        return 2
      }
      owner="$(stat -c '%u' -- "$path")"
      mode="$(stat -c '%a' -- "$path")"
      parent_owner="$(stat -c '%u' -- "$parent")"
      parent_mode="$(stat -c '%a' -- "$parent")"
      [[ "$owner" == "0" && "$mode" == "600" ]] || {
        echo "staging/production migrator lifecycle lock must be root-owned mode 0600" >&2
        return 2
      }
      [[ "$parent_owner" == "0" ]] && (( (8#$parent_mode & 8#022) == 0 )) || {
        echo "staging/production migrator lifecycle lock parent must be root-owned and non-writable" >&2
        return 2
      }
      ;;
    *)
      parent_owner="$(stat -c '%u' -- "$parent")"
      parent_mode="$(stat -c '%a' -- "$parent")"
      [[ "$parent_owner" == "$(id -u)" ]] && (( (8#$parent_mode & 8#022) == 0 )) || {
        echo "migrator lifecycle lock parent must be owned by the current user and non-writable" >&2
        return 2
      }
      if [[ -e "$path" || -L "$path" ]]; then
        [[ -f "$path" && ! -L "$path" ]] || {
          echo "migrator lifecycle lock must be a regular non-symlink file" >&2
          return 2
        }
        owner="$(stat -c '%u' -- "$path")"
        mode="$(stat -c '%a' -- "$path")"
        [[ "$owner" == "$(id -u)" && "$mode" == "600" ]] || {
          echo "migrator lifecycle lock must be owned by the current user and mode 0600" >&2
          return 2
        }
      else
        (umask 077; : >"$path"; chmod 600 "$path") || return $?
      fi
      ;;
  esac
}

acquire_migrator_lifecycle_lock() {
  command -v flock >/dev/null 2>&1 || {
    echo "flock is required for the migrator lifecycle lock" >&2
    return 127
  }
  [[ -z "$MIGRATOR_LIFECYCLE_LOCK_FD" ]] || {
    echo "migrator lifecycle lock is already held" >&2
    return 2
  }
  local path
  path="$(migrator_lifecycle_lock_path)"
  _migrator_lifecycle_lock_path_is_safe "$path" || return $?
  _migrator_lifecycle_lock_prepare_file "$path" || return $?
  if ! exec {MIGRATOR_LIFECYCLE_LOCK_FD}<>"$path"; then
    MIGRATOR_LIFECYCLE_LOCK_FD=""
    echo "migrator lifecycle lock could not be opened" >&2
    return 2
  fi
  if ! flock -n "$MIGRATOR_LIFECYCLE_LOCK_FD"; then
    eval "exec ${MIGRATOR_LIFECYCLE_LOCK_FD}>&-"
    MIGRATOR_LIFECYCLE_LOCK_FD=""
    echo "another Pinvi migrator lifecycle is already running" >&2
    return 2
  fi
  MIGRATOR_LIFECYCLE_LOCK_PATH_ACTIVE="$path"
}

release_migrator_lifecycle_lock() {
  [[ -n "$MIGRATOR_LIFECYCLE_LOCK_FD" ]] || return 0
  flock -u "$MIGRATOR_LIFECYCLE_LOCK_FD" || true
  eval "exec ${MIGRATOR_LIFECYCLE_LOCK_FD}>&-"
  MIGRATOR_LIFECYCLE_LOCK_FD=""
  MIGRATOR_LIFECYCLE_LOCK_PATH_ACTIVE=""
}
