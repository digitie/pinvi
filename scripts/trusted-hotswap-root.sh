#!/bin/sh
# M05 hotswap의 유일한 production host launcher이다.
#
# 이 파일은 root:root 0755로 /usr/local/sbin/pinvi-trusted-hotswap에 설치한다.
# 호출자 환경, PATH, Python site configuration을 절대 상속하지 않는다. 동반 entrypoint와
# config의 설치·권한 계약은 docs/runbooks/backup-restore.md를 따른다.

set -eu
unset BASH_ENV CDPATH ENV IFS
PATH=/usr/bin:/bin
export PATH

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
  echo "pinvi trusted hotswap requires root execution" >&2
  exit 3
fi

exec /usr/bin/env -i \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/python3 -I /usr/local/libexec/pinvi/trusted-hotswap-entrypoint.py "$@"
