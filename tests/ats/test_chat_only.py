"""Functional: a chat-only agent renders no RemoteMCPServer.

Installs a second release from the archive under test with
tests/ats/values-chat-only.yaml (toolset exactly ["preset:none"]) next to the
release ATS deployed, asserts an AgentTemplate without a muster binding and no
RemoteMCPServer of that name, and uninstalls it again.
"""

import logging
import os
import subprocess  # nosec: fixed argv, the archive path comes from ATS
from pathlib import Path
from typing import Iterator

import pytest
from pykube.objects import object_factory
from pytest_helm_charts.clusters import Cluster

from conftest import API_VERSION, HARNESS_LABEL

logger = logging.getLogger(__name__)

RELEASE = "ats-chat-only"
ATS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ATS_DIR.parents[1]
VALUES = ATS_DIR / "values-chat-only.yaml"


def chart_archive() -> Path:
    """The archive under test. ATS names it in ATS_CHART_PATH relative to its
    working directory (the repository root, where the CI job copies the
    archive), while pytest runs in tests/ats — so a relative name is resolved
    against the root, or `helm install` reads it as a repository reference."""
    archive = Path(os.environ["ATS_CHART_PATH"])
    if not archive.is_absolute():
        archive = REPO_ROOT / archive
    assert archive.is_file(), f"chart archive not found: {archive}"
    return archive


def helm(*args: str) -> None:
    cmd = ["helm", *args]
    logger.info("$ %s", " ".join(cmd))
    subprocess.run(cmd, check=True, timeout=300)  # nosec


@pytest.fixture(scope="module")
def chat_only_release(kube_cluster: Cluster) -> Iterator[str]:
    namespace = os.environ.get("ATS_RELEASE_NAMESPACE", "default")
    helm("install", RELEASE, str(chart_archive()), "--namespace", namespace, "--values", str(VALUES))
    try:
        yield namespace
    finally:
        helm("uninstall", RELEASE, "--namespace", namespace)


@pytest.mark.functional
def test_chat_only_agent_has_no_remotemcpserver(kube_cluster: Cluster, chat_only_release: str) -> None:
    namespace = chat_only_release
    client = kube_cluster.kube_client
    AgentTemplate = object_factory(client, API_VERSION, "AgentTemplate")
    RemoteMCPServer = object_factory(client, API_VERSION, "RemoteMCPServer")

    template = AgentTemplate.objects(client, namespace=namespace).get_by_name(RELEASE)
    assert template.labels[HARNESS_LABEL] == "kagent"
    assert template.annotations["ui.giantswarm.io/display-name"] == "ATS Chat-only Agent"
    assert "tools" not in template.obj["spec"], template.obj["spec"]

    assert RemoteMCPServer.objects(client, namespace=namespace).get_or_none(name=RELEASE) is None
