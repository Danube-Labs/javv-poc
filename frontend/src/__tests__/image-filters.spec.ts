import { describe, expect, it } from 'vitest'

import { emptySelections } from '@/filters/fields.config'
import { IMAGES_FIELDS } from '@/images/fields.config'
import { filterImages, imagesCsv, imagesFacets } from '@/images/imageFilters'
import type { ImageRow } from '@/stores/images'

const row = (over: Partial<ImageRow>): ImageRow => ({
  image_digest: 'sha256:x',
  image_repo: 'docker.io/library/nginx',
  tag: '1.21.6',
  namespaces: ['javv-smoke'],
  scanners: ['trivy'],
  crit: 0,
  high: 0,
  med: 0,
  low: 0,
  negligible: 0,
  unknown: 0,
  total: 0,
  fixable: 0,
  replicas: 1,
  trivy_count: null,
  grype_count: null,
  count_delta: null,
  '@timestamp': '2026-07-08T21:06:56+00:00',
  ...over,
})

const rows = [
  row({ image_digest: 'sha256:a', crit: 2, high: 1, total: 3, fixable: 3, namespaces: ['payments'] }),
  row({ image_digest: 'sha256:b', scanners: ['grype'], low: 4, total: 4, image_repo: 'docker.io/rancher/klipper-lb', tag: 'v0.4.17' }),
  row({ image_digest: 'sha256:c' }), // clean image
]

describe('imagesFacets (image counts, not finding counts)', () => {
  it('buckets count IMAGES with >0 of that severity; namespaces sorted by count', () => {
    const f = imagesFacets(rows)
    expect(f.severity).toEqual([
      { key: 'critical', count: 1, by_scanner: {} },
      { key: 'high', count: 1, by_scanner: {} },
      { key: 'low', count: 1, by_scanner: {} },
    ])
    expect(f.scanner).toEqual([
      { key: 'trivy', count: 2, by_scanner: {} },
      { key: 'grype', count: 1, by_scanner: {} },
    ])
    expect(f.namespaces![0]).toMatchObject({ key: 'javv-smoke', count: 2 })
  })
})

describe('filterImages (OR within a field, AND across)', () => {
  const sel = () => emptySelections(IMAGES_FIELDS)

  it('severity multi ORs; scanner and namespace match membership; fixable is a flag', () => {
    expect(filterImages(rows, { ...sel(), severity: ['critical', 'low'] }).map((r) => r.image_digest)).toEqual([
      'sha256:a',
      'sha256:b',
    ])
    expect(filterImages(rows, { ...sel(), scanner: ['grype'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), attr: ['fixable'] }).map((r) => r.image_digest)).toEqual(['sha256:a'])
    expect(filterImages(rows, { ...sel(), namespace: ['payments'] })).toHaveLength(1)
  })

  it('scanner matches the D5b pair evidence, not just the committing cycle (corpus shape)', () => {
    // the real corpus: every doc committed by trivy's cycle, grype evidenced only by the pair
    const corpus = [
      row({ image_digest: 'sha256:p', scanners: ['trivy'], trivy_count: 761, grype_count: 746, count_delta: 15 }),
      row({ image_digest: 'sha256:q', scanners: ['trivy'], trivy_count: 5, grype_count: null }),
    ]
    expect(filterImages(corpus, { ...sel(), scanner: ['grype'] }).map((r) => r.image_digest)).toEqual(['sha256:p'])
    expect(imagesFacets(corpus).scanner).toEqual([
      { key: 'trivy', count: 2, by_scanner: {} },
      { key: 'grype', count: 1, by_scanner: {} },
    ])
  })

  it('q contains-matches repo, tag, and namespaces', () => {
    expect(filterImages(rows, { ...sel(), q: ['klipper'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['v0.4'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['payments'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['nope'] })).toHaveLength(0)
  })

  it('empty selections pass everything (clean images included)', () => {
    expect(filterImages(rows, sel())).toHaveLength(3)
  })
})

describe('imagesCsv', () => {
  it('one line per row, D5b pair blank when absent, quoted when needed', () => {
    const csv = imagesCsv([row({ tag: 'a,b' })])
    const lines = csv.split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain('count_delta')
    expect(lines[1]).toContain('"a,b"')
  })
})
