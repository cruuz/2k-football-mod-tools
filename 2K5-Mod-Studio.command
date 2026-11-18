#!/bin/bash
# Finder may start a link outside the extracted archive. BSD readlink has no portable -f option.
set -u
launcher=${BASH_SOURCE[0]}
[[ $launcher == /* ]] || launcher="$PWD/$launcher"
while [[ -L $launcher ]]; do
    link=$(readlink "$launcher") || exit 1
    if [[ $link == /* ]]; then launcher=$link; else launcher="${launcher%/*}/$link"; fi
done
cd -P "${launcher%/*}" || exit 1
if [[ ! -f packaging/posix_studio.sh ]]; then
    printf '%s\n' 'Extract the entire Studio archive, then open the .command file inside it.' >&2
    exit 1
fi
exec /bin/bash packaging/posix_studio.sh 2k5 macos "$@"
