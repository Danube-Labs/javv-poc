"""scan_order allocation, scanner side (D45). The backend mints the ordering key — a strictly
increasing per-(cluster, scanner) sequence, never a clock — via `POST /api/v1/scan-runs` at cycle
start. Fail-closed like the D43 scope fetch: **None on any failure = do not scan this cycle**
(an unordered scan could be silently dropped by the watermark CAS, or worse, mis-ordered)."""

import httpx


def fetch_scan_order(http: httpx.Client, *, token: str | None) -> int | None:
    """The next `scan_order` for this scanner's (cluster, scanner), or None on any failure."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = http.post("/api/v1/scan-runs", headers=headers)
        resp.raise_for_status()
        order = resp.json()["scan_order"]
        if not isinstance(order, int) or order <= 0:
            return None
        return order
    except Exception:
        return None
