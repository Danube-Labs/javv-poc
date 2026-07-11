/** Pure builder: the M8b two-step image-at-T params (D38/H6). TWO DISTINCT reads, never
 * conflated — `runtime_inventory_at_T` asks "was this digest in the running set at T?"
 * (the committed-inventory read), `vulns_as_scanned_at_T` asks "what did this scanner's
 * latest committed scan ≤ T say?" (the findings read, single-scanner). `t === null` = NOW:
 * both param sets omit `as_of` entirely, so the branch is observable in the emitted params. */

export interface ImageAtTQueries {
  runtime_inventory_at_T: { cluster_id: string; as_of?: string }
  vulns_as_scanned_at_T: {
    cluster_id: string
    image_digest: string
    scanner: string
    as_of?: string
  }
}

export function buildImageAtTQuery(
  clusterId: string,
  imageDigest: string,
  scanner: string,
  t: string | null,
): ImageAtTQueries {
  const asOf = t === null ? {} : { as_of: t }
  return {
    runtime_inventory_at_T: { cluster_id: clusterId, ...asOf },
    vulns_as_scanned_at_T: {
      cluster_id: clusterId,
      image_digest: imageDigest,
      scanner,
      ...asOf,
    },
  }
}
