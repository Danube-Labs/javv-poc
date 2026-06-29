"""JAVV in-cluster vulnerability scanner.

Discovers running images, scans each with Trivy and Grype (per-scanner, never merged),
normalizes severity, builds a current-only envelope, and pushes it to the backend.
See development/bolts/M0-scanners/README.md.
"""

__version__ = "0.1.0"
