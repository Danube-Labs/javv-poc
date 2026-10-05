#!/bin/sh
# The init container of each scanner run (issue 725): refreshes the scanner's vuln DB in its cache
# volume, from the vendor's source or the one set in vulnDb. The scan then runs with updates off,
# so every image in a cycle is checked against one DB and nothing upstream is called mid-cycle.
# A failed refresh falls back to the cached DB; with none cached, the run fails here and says so.
# One JSON line per outcome, in the shape the scanner's own log lines have.
log() {
  printf '{"timestamp":"%s","level":"%s","event":"%s","scanner":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$JAVV_SCANNER"
}

case "$JAVV_SCANNER" in
  trivy)
    refresh() { trivy image --download-db-only --quiet && trivy image --download-java-db-only --quiet; }
    cached() { [ -s "$TRIVY_CACHE_DIR/db/trivy.db" ] && [ -s "$TRIVY_CACHE_DIR/java-db/trivy-java.db" ]; }
    ;;
  grype)
    refresh() { grype db update --quiet >/dev/null; }
    cached() { grype db status --quiet >/dev/null 2>&1; }
    ;;
  *)
    log error "unknown scanner, no vuln db refreshed"
    exit 2
    ;;
esac

if refresh; then
  log info "vuln db refreshed"
  exit 0
fi
if cached; then
  log warning "vuln db refresh failed, scanning with the cached db"
  exit 0
fi
log error "vuln db refresh failed and none is cached, this cycle does not scan"
exit 1
