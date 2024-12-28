"""Tests conftest."""

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
CLUSTER_CRD = BASE_DIR / "crd_chart" / "crds" / "ArkCluster.yml"
