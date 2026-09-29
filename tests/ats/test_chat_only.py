"""Functional: a chat-only agent reaches Ready with no RemoteMCPServer.

A release with tests/ats/values-chat-only.yaml (toolset exactly
["preset:none"]) renders an Agent without a muster binding and no
RemoteMCPServer of that name; on the platform Harness it is compiled and
booted like any other agent. The runtime is the one the smoke brought
up (conftest.py: the fixture finds it installed).
"""

import logging
from pathlib import Path
from typing import Callable

import pytest

from conftest import AGENTS, HARNESS, KAGENT_NAMESPACE, Kube, agent_generation, assert_all_conditions_true, remote_mcp_server, wait_agent_ready

logger = logging.getLogger(__name__)

RELEASE = "ats-chat-only"
VALUES = Path(__file__).resolve().parent / "values-chat-only.yaml"


@pytest.mark.functional
def test_chat_only_agent_reaches_ready_without_a_remotemcpserver(kube: Kube, release: Callable[..., None]) -> None:
    release(RELEASE, VALUES)
    generation = agent_generation(kube, RELEASE)
    status = wait_agent_ready(kube, RELEASE)
    assert_all_conditions_true(status, generation)

    agent = kube.get(AGENTS, RELEASE, namespace=KAGENT_NAMESPACE)
    assert agent
    assert agent["spec"]["harnessRef"] == {"name": HARNESS}
    assert agent["metadata"]["annotations"]["ui.giantswarm.io/display-name"] == "ATS Chat-only Agent"
    assert "tools" not in agent["spec"]["template"], agent["spec"]["template"]
    assert remote_mcp_server(kube, RELEASE) is None
    logger.info("%s Ready on %s without a RemoteMCPServer", RELEASE, HARNESS)
