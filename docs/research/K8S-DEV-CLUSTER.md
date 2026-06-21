# JAVV — Dev/test Kubernetes cluster options

> Research agent output, captured 2026-06-20. Grounded in current (2025–2026) pricing/limits. Verify
> free-tier terms before relying on them — they change. Companion to the Ubuntu-VM plan ([[dev-environment]]).

## What JAVV needs from a dev cluster
Run pods + **CronJobs**; pull + scan **real images** (registry egress + disk/CPU — Trivy/Grype DBs are
hundreds of MB, layer-unpack + scan is CPU/I/O-heavy); reachable **kube-apiserver** with RBAC to list
workloads and read the **`kube-system` namespace UID** (= `cluster_id`); ideally **2–3 registerable
clusters** for the multi-cluster story. Sizing driver is the scan workload: ~2 vCPU / 2–4 GB free per
scanning node minimum.

## TRACK 1 — Local on the Ubuntu VM

**k3s is a good fit** (single ~70 MB binary, bundles containerd, SQLite default, 2 vCPU/2 GB floor).
```bash
curl -sfL https://get.k3s.io | sh -   # kubeconfig at /etc/rancher/k3s/k3s.yaml
```
VM caveats: **no nested virtualization needed** (runs containers, not VMs — the big reason k3s/k3d/kind
beat minikube here); budget ≥2 vCPU / ≥4 GB / ~20–40 GB disk (image layers + scanner DBs under
`/var/lib/rancher/k3s/`); modern Ubuntu cgroup v2 is fine; default Traefik+ServiceLB (disable Traefik to
save RAM if unused); disable swap if kubelet complains. Single combined server+agent node is all you need.

**Comparison for this use case:**
| Tool | Nested-virt? | Footprint | Multi-cluster on one box | Fit |
|---|---|---|---|---|
| k3s | No | Lowest | Awkward (separate data-dirs/ports) | Great "real node"; clunky for many |
| **k3d** (k3s-in-Docker) | No (just Docker) | ~420–500 MiB/cluster | **Excellent** (`k3d cluster create a/b/c`) | **Best for multi-cluster sim** |
| kind | No (just Docker) | Low | Excellent | Good; most vanilla fidelity; manual image-load |
| minikube | **Often yes (VM driver)** | Highest | Profiles, heavier | **Avoid in nested VM** |
| microk8s | No | Medium | Weak multi-cluster | OK; snap quirks |

**Recommendation: k3d as primary local driver** (k3s-in-Docker → 2–3 isolated clusters, each with its own
apiserver + distinct `kube-system` UID). Keep a host k3s install as the "one realistic node." Skip minikube.

**Stand up 2–3 simulated clusters (distinct `cluster_id`s):**
```bash
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
k3d cluster create alpha   --servers 1 --agents 0 -p "8081:80@loadbalancer"
k3d cluster create bravo   --servers 1 --agents 0 -p "8082:80@loadbalancer"
k3d cluster create charlie --servers 1 --agents 0 -p "8083:80@loadbalancer"
for c in alpha bravo charlie; do echo -n "$c -> "; \
  kubectl --context k3d-$c get namespace kube-system -o jsonpath='{.metadata.uid}'; echo; done
```
Three real, distinct `cluster_id`s to validate per-cluster index routing never collides. Caveat: k3d
clusters share the host kernel/CPU/disk — fine for functional multi-cluster wiring, **don't benchmark scan
throughput** this way. Teardown: `k3d cluster delete alpha bravo charlie`.

## TRACK 2 — Free / very cheap online managed k8s

**Key distinction: "free control plane" ≠ "free cluster."** Most providers give the apiserver free, charge
for worker nodes. Genuinely-free-including-compute: Oracle Always Free and GKE's monthly credit (control-
plane fee only).

- **Oracle Cloud Always Free (OKE)** — only "free including real compute." Basic OKE control plane free;
  ARM Ampere A1 allotment. **2026 gotcha:** Always-Free Ampere cut to **2 OCPU / 12 GB** around
  **2026-06-15** (from 4/24). Still runs Trivy/Grype for one cluster. Other gotchas: A1 capacity chronically
  out of stock; everything is **arm64** (scanner images must be multi-arch — Trivy/Grype are); historical
  idle-reclaim. Multi-cluster impractical on the free allotment.
- **Google GKE** — free *management fee* ($74.40/mo credit covers one zonal/Autopilot cluster's $0.10/hr
  fee), **NOT free nodes**. With Autopilot a tiny Trivy workload may be a few $/mo in pod-seconds; the
  **$300/90-day** new-account credit makes the trial window truly free. Good "realistic remote test."

**Cheap paid (control plane free, pay nodes):**
| Provider | Control plane | Realistic min/mo | Notes |
|---|---|---|---|
| **Hetzner** (DIY k3s on Cloud VMs) | n/a (self-managed) | **~$5–6/mo** (CX22 2 vCPU/4 GB) | Cheapest *real node*; reuses your k3s plan |
| Civo | Free | ~$20/mo | k3s-based, fast spin-up; $250 first-month credit |
| DigitalOcean DOKS | Free (HA $40) | ~$12–24/mo | mature; new-user credit |
| Linode/Akamai LKE | Free (HA $60) | ~$24/mo | $100 signup credit |
| Vultr | Free | ~$20–30/mo | drop LB → ~$20 |
| Scaleway Kapsule / OVH | Free | ~$15–25/mo | EU |

Real apiserver + cheap multi-cluster: Civo / DO / Linode (add a 2nd cheap cluster = another node bill), or
**2–3 Hetzner CX22 VMs running k3s (~€15/mo total)** — best price/realism, mirrors the local k3s story.

## Recommendation
- **(a) Day-to-day local dev → k3d on the Ubuntu VM.** k3s-in-Docker, no nested virt (decisive in a nested
  VM), smallest footprint, 2–3 isolated clusters in seconds — exactly what the per-`cluster_id` partition
  story needs. Keep a host k3s as the "one real node" check. Give the VM ≥2 vCPU / ≥4 GB / ~30 GB disk.
- **(b) Realistic remote test → 2–3 Hetzner CX22 + k3s (~€15/mo)**, or **Oracle OKE Always Free** for one
  forever-free real cluster (plan for arm64 + A1 scarcity + the June-2026 cut), or **GKE Autopilot** under
  the $300/90-day trial for a polished managed demo. Don't pay monthly managed fees until you specifically
  need a managed control plane — JAVV reads a standard apiserver, so self-managed k3s gives identical
  fidelity for a fraction of the cost.
