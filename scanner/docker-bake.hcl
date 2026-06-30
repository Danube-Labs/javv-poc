# Build the compatible, pinned scanner images from one Dockerfile per scanner (M0b / D41).
# One Dockerfile, built across a matrix of versions → N pinned image tags. The version lists
# default to the current pins here but are overridden in CI from versions.yaml (single source, D42).
# Run from the scanner/ dir (context = "."), e.g.:
#   docker buildx bake -f docker-bake.hcl --print
#   docker buildx bake -f docker-bake.hcl --set '*.platform=linux/amd64'
variable "REGISTRY" {
  default = "ghcr.io/danube-labs"
}
variable "TRIVY_VERSIONS" {
  default = "0.71.2,0.70.0"
}
variable "GRYPE_VERSIONS" {
  default = "0.115.0,0.114.0"
}

group "default" {
  targets = ["trivy", "grype"]
}

target "trivy" {
  name       = "trivy-${replace(ver, ".", "-")}"
  matrix     = { ver = split(",", TRIVY_VERSIONS) }
  context    = "."
  dockerfile = "Dockerfile.trivy"
  args       = { TRIVY_VERSION = ver }
  tags       = ["${REGISTRY}/javv-scanner-trivy:${ver}"]
}

target "grype" {
  name       = "grype-${replace(ver, ".", "-")}"
  matrix     = { ver = split(",", GRYPE_VERSIONS) }
  context    = "."
  dockerfile = "Dockerfile.grype"
  args       = { GRYPE_VERSION = ver }
  tags       = ["${REGISTRY}/javv-scanner-grype:${ver}"]
}
