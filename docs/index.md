# JAVV operator docs

JAVV finds the container images running in your Kubernetes clusters, scans them with Trivy and
Grype side by side, and gives every vulnerability its own audited triage lifecycle. These pages
are for the people who install and run it.

## Start here

| To | Read |
|---|---|
| Install JAVV with docker compose or Helm | [Deploying](DEPLOYING.md) |
| Run the scanners in the clusters you watch | [Deploying: point scanners at it](DEPLOYING.md#point-scanners-at-it) and the [scanner chart](../deploy/helm/javv-scanner/README.md) |
| Check which scanner and OpenSearch versions a release supports | [Supported versions](supported-versions.md) |
| Change a setting | [Configuration](CONFIGURATION.md) |
| Upgrade, or roll back | [Upgrading](UPGRADING.md) and the [release notes](../CHANGELOG.md) |
| Verify the published images and charts | [Deploying: verify the images and charts](DEPLOYING.md#verify-the-images-and-charts) |
| Script against JAVV, or push findings from your own tooling | [API](API.md) and the [ingest contract](INGEST-CONTRACT.md) |
| Report a security issue | [Security](../SECURITY.md) |

Each JAVV release has its own version of these docs; pick it in the version menu.
