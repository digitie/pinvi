#!/bin/sh

set -eu

build_environment=${1:-}
source_revision=${2:-}

is_commit() {
    case "$1" in
        ''|*[!0-9a-f]*) return 1 ;;
    esac
    [ "${#1}" -eq 40 ]
}

case "$build_environment" in
    development|test|smoke) ;;
    staging|production)
        is_commit "$source_revision" || {
            echo 'staging/production image requires an exact source commit' >&2
            exit 2
        }
        ;;
    *)
        echo 'PINVI_BUILD_ENVIRONMENT is not canonical' >&2
        exit 2
        ;;
esac

if [ "$source_revision" != development ]; then
    is_commit "$source_revision" || {
        echo 'PINVI_SOURCE_REVISION must be development or an exact source commit' >&2
        exit 2
    }
fi
