#!/usr/bin/env bash
# Publish one verified lane at a time in an ephemeral partial clone.
set -euo pipefail
code=$1
case "$code" in A01|A02|A03|A04|A05|A06|B07|B08|C09|C10|C11|C12) ;; *) exit 2;; esac
stage=$(mktemp -d "$RUNNER_TEMP/confirm-lane.XXXXXXXX")
repo=$stage/repo
dir="research/ch3_center_confirmation/lanes/$code"
git init -q "$repo"
git -C "$repo" remote add origin "https://github.com/$GITHUB_REPOSITORY.git"
git -C "$repo" config remote.origin.promisor true
git -C "$repo" config remote.origin.partialclonefilter blob:none
git -C "$repo" config user.name 'github-actions[bot]'
git -C "$repo" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git -C "$repo" fetch -q --filter=blob:none --depth=1 origin "refs/heads/$GITHUB_REF_NAME"
previous=$(git -C "$repo" rev-parse FETCH_HEAD)
test "$previous" = "$(cat "$PUBLICATION_HEAD")"
git -C "$repo" sparse-checkout init --no-cone
git -C "$repo" sparse-checkout set --no-cone '/research/ch3_center_confirmation/START' "/$dir/"
git -C "$repo" checkout -q --detach "$previous"
cd "$repo"
mkdir -p "$dir"
gh run download "$SCIENCE_RUN" --repo "$GITHUB_REPOSITORY" --name "lane-$code" --dir "$dir"
(cd "$dir" && sha256sum --quiet -c SHA256SUMS)
gh run download "$GITHUB_RUN_ID" --repo "$GITHUB_REPOSITORY" --name "audit-$code" --dir "$stage/audit"
(cd "$stage/audit" && sha256sum --quiet -c AUDIT_SHA256SUMS)
cp "$stage/audit/reduced.json.gz" "$dir/reduced.json.gz"
for rep in 1 2 3; do
  cp "$stage/audit/r$rep/final_endpoints.tar.gz" "$dir/r$rep/final_endpoints.tar.gz"
  find "$dir/r$rep" -type f -print0 > "$stage/files"
  git add --pathspec-from-file="$stage/files" --pathspec-file-nul
  git diff --cached --quiet -- . ":(exclude)$dir/r$rep/**"
  if ! git diff --cached --quiet; then
    git diff --cached --stat | tail -1
    git commit -qm "Archive $code repetition $rep cold cells and verified physical traces"
    git push -q origin HEAD:"refs/heads/$GITHUB_REF_NAME"
  fi
done
cp "$stage/audit/AUDIT_SHA256SUMS" "$dir/AUDIT_SHA256SUMS"
git add -- "$dir/SHA256SUMS" "$dir/reduced.json.gz" "$dir/AUDIT_SHA256SUMS"
if ! git diff --cached --quiet; then
  git commit -qm "Seal $code lane checksums, plan identities and timing ledger"
  git push -q origin HEAD:"refs/heads/$GITHUB_REF_NAME"
fi
git rev-parse HEAD > "$PUBLICATION_HEAD"
cd "$RUNNER_TEMP"
# Temporary clone and downloads are reproducible from the two verified remote archives.
case "$stage" in "$RUNNER_TEMP"/confirm-lane.*) rm -rf -- "$stage";; *) exit 3;; esac
