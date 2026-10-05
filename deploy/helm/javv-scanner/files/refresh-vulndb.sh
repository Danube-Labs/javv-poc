#!/bin/sh
# The init container of each scanner run (issue 725): refreshes the scanner's vuln DB in its cache
# volume, from the vendor's source or the one set in vulnDb. The scan then runs with updates off,
# so every image in a cycle is checked against one DB and nothing upstream is called mid-cycle.
# Whatever the refresh did, the run goes on only with a DB the scanner can read: a current one, or
# the cached one when the refresh failed. A DB that cannot be read is dropped and fetched once
# more (its metadata may call it current, and the refresh would then never replace it). With no
# readable DB, the run fails here and says so.
# One JSON line per outcome, in the shape the scanner's own log lines have.
log() {
  printf '{"timestamp":"%s","level":"%s","event":"%s","scanner":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$JAVV_SCANNER"
}

case "$JAVV_SCANNER" in
  trivy)
    refresh() { trivy image --download-db-only --quiet && trivy image --download-java-db-only --quiet; }
    # A lookup, not a look at the files: `trivy version` reads only metadata.json and reports a
    # cut trivy.db as fine, while a scan of it crashes. This image's own Debian packages are
    # always there, and the scan takes a second or two.
    usable() {
      [ -s "$TRIVY_CACHE_DIR/java-db/trivy-java.db" ] &&
        trivy rootfs --skip-db-update --skip-java-db-update --skip-check-update --scanners vuln \
          --pkg-types os --skip-dirs /proc --skip-dirs /sys --skip-dirs /var/cache/javv \
          --quiet / >/dev/null 2>&1
    }
    drop() { rm -r -f "$TRIVY_CACHE_DIR/db"; }
    ;;
  grype)
    refresh() { grype db update --quiet >/dev/null; }
    usable() { grype db status --quiet >/dev/null 2>&1; }
    drop() { grype db delete --quiet >/dev/null 2>&1; }
    ;;
  *)
    log error "unknown scanner, no vuln db refreshed"
    exit 2
    ;;
esac

refreshed=no
refresh && refreshed=yes
if ! usable; then
  log warning "vuln db unreadable, fetching it again"
  drop
  refreshed=no
  refresh && refreshed=yes
fi
if usable; then
  if [ "$refreshed" = yes ]; then
    log info "vuln db up to date"
  else
    log warning "vuln db refresh failed, scanning with the cached db"
  fi
  exit 0
fi
if [ "$refreshed" = yes ]; then
  log error "vuln db refreshed but unreadable, this cycle does not scan"
else
  log error "vuln db refresh failed and no readable one is cached, this cycle does not scan"
fi
exit 1
