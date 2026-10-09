# Sizing OpenSearch

JAVV keeps everything in one OpenSearch: the scanners' results, their history, and every triage
decision. This page says what grows, which limit you meet first, how to see where you are, and
what to change. The figures marked *measured* come from one development install with 4 clusters
and about 1.7 million documents, on OpenSearch 3.9.0 with a 1 GB heap.

## What takes the space

Every scan writes a full snapshot of what it found: one document per finding, per image, per
scanner, per scan cycle. That history is what time travel reads, and it is almost all of the
store.

| Index | What it holds | Measured |
|---|---|---|
| `javv-finding-occurrences-<cluster>-*` | the history: one document per finding per scan | 1.54 M documents, 436 MB, about **280 bytes each** |
| `findings` | the current state of each finding, with its triage | 123 k documents, 60 MB, about 490 bytes each |
| `javv-scan-events-*`, `javv-images-*`, `javv-inventory-runs-*`, `javv-ingest-failures-*` | one document per scan or per image per cycle | under 6 MB together |
| `system-*` | users, sessions, decisions, the audit log, settings, reports | under 4 MB together |

Sizes are of the primary copy. To estimate the history for your fleet:

```text
documents per day ≈ for each scanner: images × findings per image × scan cycles per day
history size      ≈ documents per day × (retention days + 30) × 280 bytes
```

The `+ 30` is because an index is dropped only when its newest document is older than the
retention, and an index takes up to 30 days of documents before it rolls over. The scanner
chart runs each scanner every 6 hours by default (4 cycles a day). For example, 500 images with
40 findings each, two scanners, 4 cycles a day and the default 90-day retention:
500 × 40 × 2 × 4 = 160,000 documents a day, × 120 days × 280 bytes ≈ 5.4 GB.

Reports exported to run later are stored in OpenSearch too until they expire
(`JAVV_EXPORT_TTL_HOURS`, 24 h by default), each capped at `JAVV_EXPORT_MAX_BYTES` (500 MiB).

## The first limit: shards

Each index has **one primary shard**, and each cluster you monitor has five series of them. A
series rolls over to a new index after 30 days, 5 million documents or 50 GB, whichever comes
first, and an index is dropped once all of its data is older than the cluster's retention. With
the defaults (30-day rollover, 90-day retention), each series keeps about five indices, so
**each monitored cluster holds about 25 shards**. On top of that are about 15 shards that do not
grow with clusters, and the audit log, which rolls every 30 days and is never dropped.

OpenSearch allows **1,000 shards per node** by default (`cluster.max_shards_per_node`). With
the default settings that is room for **about 38 monitored clusters on one node**. This is
arithmetic from the defaults, not a load test. Every shard also costs heap, however small it is.

To see where you are: **Settings › Data & OpenSearch** shows the active shards on its runtime
card, or ask OpenSearch with `GET _cluster/health` (`active_shards`).

To make room, in order of preference:

1. **Shorter retention** for clusters that don't need long history: **Settings › Data &
   OpenSearch › Retention**, per cluster. It also shortens how far back time travel reaches.
2. **Longer rollover** (the same panel): fewer, larger indices. A rollover still happens at
   5 million documents or 50 GB.
3. **Retire clusters that went silent.** A retired cluster stops counting once it is deleted
   (**Settings › Cluster**).
4. **More nodes**, with an OpenSearch of your own (below), or a higher
   `cluster.max_shards_per_node` with more heap to match.

## Memory

The default heap is **1 GB**: `OPENSEARCH_JAVA_OPTS` in the compose file and `opensearchJavaOpts`
in the `javv-opensearch` chart. *Measured:* 4 clusters, 1.7 million documents and 42 shards
used about half of it.

Raise the heap when it stays high, or when OpenSearch's log shows `circuit_breaking_exception`:
the store is then refusing work to protect its memory. Give OpenSearch
about twice the heap as memory, since it also needs memory outside the heap, and keep the heap
below 32 GB. In compose, set `OPENSEARCH_JAVA_OPTS` (for example `-Xms2g -Xmx2g`); with the chart,
set `opensearchJavaOpts` and the pod's memory `resources` together.

## Disk

At **95 %** disk use (OpenSearch's flood-stage watermark) OpenSearch makes the indices
read-only. Writes then fail, and JAVV answers scanner pushes with **503** (a write the store
refuses is reported as `storage_error`): the scanners retry with backoff and, when their retries
run out, keep the push in their dead-letter file and scan the image again next cycle. Nothing already stored is lost, but new scans wait until there is room.

- Keep use **under about 80 %** so a burst of scans never reaches the stages above.
- **Snapshots are written inside the data volume** (`path.repo` is
  `/usr/share/opensearch/data/snapshots` in both the compose file and the chart), so they count
  against the same disk. Delete old ones, or point the repository at other storage.
- Shorter retention frees disk the night after you save it: the lifecycle job drops whole
  indices (`JAVV_JOB_LIFECYCLE_SWEEP_CRON`, 03:00 by default).

## Beyond one node

The compose file and the `javv-opensearch` chart run **one OpenSearch node**, by design; the chart
refuses any other setting. For more capacity or for a store that survives a node failure, run an
OpenSearch of your own with more nodes and replica shards, and point JAVV at it: see
[Deploying: an OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own). JAVV needs no
change for that, and the [multi-pod page](multi-pod.md) says what does and doesn't scale on
JAVV's side.
