"""Functional: a chat-only agent reaches Ready with no RemoteMCPServer.

A release with tests/ats/values-chat-only.yaml (toolset exactly
["preset:none"]) renders an AgentTemplate without a muster binding and no
RemoteMCPServer of that name; on the platform Harness it is admitted, compiled
and booted like any other template. The runtime is the one the smoke brought
up (conftest.py: the fixture finds it installed).
"""

import logging
from pathlib import Path
from typing import Callable

import pytest

from conftest import HARNESS, HARNESS_LABEL, KAGENT_NAMESPACE, Kube, assert_all_conditions_true, remote_mcp_server, template_generation, wait_template_ready

logger = logging.getLogger(__name__)

RELEASE = "ats-chat-only"
VALUES = Path(__file__).resolve().parent / "values-chat-only.yaml"


@pytest.mark.functional
def test_chat_only_agent_reaches_ready_without_a_remotemcpserver(kube: Kube, release: Callable[..., None]) -> None:
    release(RELEASE, VALUES)
    generation = template_generation(kube, RELEASE)
    entry = wait_template_ready(kube, RELEASE)
    assert_all_conditions_true(entry, generation)

    template = kube.get("agenttemplates.kagent.dev", RELEASE, namespace=KAGENT_NAMESPACE)
    assert template
    assert template["metadata"]["labels"][HARNESS_LABEL] == HARNESS
    assert template["metadata"]["annotations"]["ui.giantswarm.io/display-name"] == "ATS Chat-only Agent"
    assert "tools" not in template["spec"], template["spec"]
    assert remote_mcp_server(kube, RELEASE) is None
    logger.info("%s Ready on %s without a RemoteMCPServer", RELEASE, HARNESS)
