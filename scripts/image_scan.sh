#!/usr/bin/env bash
# Scan container images for critical CVEs (ROADMAP-100 010): `scripts/image_scan.sh <image> [<image> …]`.
#
# Trivy is fetched as a pinned release tarball and checked against the SHA-256 below before it runs — not through
# aquasecurity/trivy-action or setup-trivy, whose tags were force-pushed to malicious commits in March 2026
# (CVE-2026-33634). A changed asset or a re-pointed tag fails the checksum. To upgrade: pick a release some weeks
# old, copy the four lines from its trivy_<version>_checksums.txt, and re-run.
#
# Fails on CRITICAL vulnerabilities that have a fix (--ignore-unfixed: one with no fixed version available is
# reported in the scan's output but cannot be acted on here). Accepted findings go in infra/runtime/trivyignore,
# one CVE per line with the reason and a review date.
set -euo pipefail

VERSION=0.75.0
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) ASSET=Linux-64bit SHA=c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f ;;
  Linux-aarch64) ASSET=Linux-ARM64 SHA=a1ee9f6ffb7d112b64ff726a2a0717c21175c1114361391f4a132956751a13b3 ;;
  Darwin-arm64) ASSET=macOS-ARM64 SHA=4a77108cccf8e55c8d6823e1e759939a622277e66cd0daa3c1fc621ed69e4568 ;;
  Darwin-x86_64) ASSET=macOS-64bit SHA=291edaa9778acbe4693d067b5ad60ee11570e5ac68296e85595417528ca641e4 ;;
  *) echo "no pinned Trivy build for $(uname -s)-$(uname -m)" >&2; exit 2 ;;
esac

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR=${TRIVY_DIR:-$ROOT/.data/tools/trivy-$VERSION}
if [ ! -x "$DIR/trivy" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  tarball="trivy_${VERSION}_${ASSET}.tar.gz"
  curl -fsSL -o "$tmp/$tarball" "https://github.com/aquasecurity/trivy/releases/download/v${VERSION}/${tarball}"
  got=$( (sha256sum "$tmp/$tarball" 2>/dev/null || shasum -a 256 "$tmp/$tarball") | cut -d' ' -f1)
  if [ "$got" != "$SHA" ]; then
    echo "checksum mismatch for $tarball: got $got, pinned $SHA" >&2
    exit 1
  fi
  mkdir -p "$DIR"
  tar -xzf "$tmp/$tarball" -C "$DIR" trivy
fi

status=0
for image in "$@"; do
  echo "== $image"
  "$DIR/trivy" image --quiet --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 \
    --ignorefile "$ROOT/infra/runtime/trivyignore" "$image" || status=1
done
exit $status
