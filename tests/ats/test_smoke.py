"""Smoke: a release of the chart reaches Ready on the platform Harness.

On the runtime the ``runtime`` fixture brings up (conftest.py: Substrate,
kagent and the Harness `kagent`, all before any release of this chart), two
releases of the archive under test are installed into the Harness's namespace:

  * `agent` with tests/ats/values-smoke.yaml — a display name, an icon, a
    toolset, a narrowed muster binding, a public git skill pinned to a commit,
    extra labels and annotations: every field the chart maps. The template
    is admitted, compiled and booted into a golden snapshot (the skill is
    materialised on the way), and the agent's RemoteMCPServer is accepted with
    no failed condition.
  * `ats-defaults` with the chart's default values — the smallest release an
    operator can install. Ready too, with its RemoteMCPServer (the default
    toolset binds muster).

Ready means compiled, admitted and bootable on the platform's runtime; no
model is called (the provider key is a placeholder).
"""

import logging
from pathlib import Path
from typing import Callable

import pytest

from conftest import (
    API_VERSION,
    DISCOVERY_LABEL,
    FIRST_BOOT_TIMEOUT_S,
    HARNESS,
    HARNESS_LABEL,
    KAGENT_NAMESPACE,
    TOOLSET_HEADER,
    Kube,
    assert_all_conditions_true,
    assert_server_accepted,
    remote_mcp_server,
    template_generation,
    wait_template_ready,
)

logger = logging.getLogger(__name__)

SMOKE_RELEASE = "agent"
SMOKE_VALUES = Path(__file__).resolve().parent / "values-smoke.yaml"
DEFAULTS_RELEASE = "ats-defaults"


@pytest.mark.smoke
def test_smoke_release_reaches_ready_with_a_git_skill(kube: Kube, release: Callable[..., None]) -> None:
    release(SMOKE_RELEASE, SMOKE_VALUES)
    generation = template_generation(kube, SMOKE_RELEASE)
    entry = wait_template_ready(kube, SMOKE_RELEASE, timeout=FIRST_BOOT_TIMEOUT_S)
    assert_all_conditions_true(entry, generation)
    assert entry["harness"] == HARNESS
    assert entry["latestSuccessfulRevision"] == entry["desiredRevision"]
    logger.info("%s Ready on %s at revision %s (warnings: %s)", SMOKE_RELEASE, HARNESS, entry["desiredRevision"], entry.get("warnings") or "none")

    template = kube.get("agenttemplates.kagent.dev", SMOKE_RELEASE, namespace=KAGENT_NAMESPACE)
    assert template
    # The contract the chart renders from values-smoke.yaml.
    labels, annotations, spec = template["metadata"]["labels"], template["metadata"]["annotations"], template["spec"]
    assert template["apiVersion"] == API_VERSION
    assert labels[HARNESS_LABEL] == HARNESS
    assert labels["app.kubernetes.io/instance"] == SMOKE_RELEASE
    assert labels["giantswarm.io/owner"] == "ats"
    assert annotations["ui.giantswarm.io/display-name"] == "ATS Smoke Agent"
    assert annotations["ui.giantswarm.io/icon-url"] == "https://avatars.example.com/ats-smoke.svg"
    assert annotations["giantswarm.io/scenario"] == "smoke"
    assert spec["modelConfig"] == {"name": "default-model-config"}
    assert spec["description"] == "Exercises the chart's field mapping on the platform's runtime."
    assert spec["systemPrompt"] == "You are the chart's smoke test. Be brief."
    assert spec["skills"] == [
        {
            "name": "agent-self-awareness",
            "source": {
                "git": {"url": "https://github.com/giantswarm/agent-skills", "commit": "cb1fb768bbbbcaa035b884a99ad308b14f846468"},
                "path": "agent-self-awareness",
            },
        }
    ]
    assert spec["tools"] == [{"mcp": {"server": {"kind": "RemoteMCPServer", "name": SMOKE_RELEASE}, "tools": ["list_tools", "call_tool"]}}]

    server = remote_mcp_server(kube, SMOKE_RELEASE)
    assert server, f"RemoteMCPServer {SMOKE_RELEASE} was not rendered"
    assert server["metadata"]["labels"][DISCOVERY_LABEL] == "disabled"
    assert HARNESS_LABEL not in server["metadata"]["labels"]
    assert server["spec"]["url"] == "http://muster.agent-platform.svc.cluster.local:8090/mcp"
    assert server["spec"]["protocol"] == "STREAMABLE_HTTP"
    assert server["spec"]["headersFrom"] == [{"name": TOOLSET_HEADER, "value": "preset:read-only,server:mcp-kubernetes"}]
    assert not [h for h in server["spec"]["headersFrom"] if h["name"].lower() == "authorization"]
    assert_server_accepted(server)


@pytest.mark.smoke
def test_default_values_reach_ready_with_a_remotemcpserver(kube: Kube, release: Callable[..., None]) -> None:
    release(DEFAULTS_RELEASE)
    generation = template_generation(kube, DEFAULTS_RELEASE)
    entry = wait_template_ready(kube, DEFAULTS_RELEASE)
    assert_all_conditions_true(entry, generation)

    template = kube.get("agenttemplates.kagent.dev", DEFAULTS_RELEASE, namespace=KAGENT_NAMESPACE)
    assert template
    assert template["metadata"]["labels"][HARNESS_LABEL] == HARNESS
    assert template["spec"]["modelConfig"] == {"name": "default-model-config"}
    assert template["spec"]["tools"] == [{"mcp": {"server": {"kind": "RemoteMCPServer", "name": DEFAULTS_RELEASE}}}]

    server = remote_mcp_server(kube, DEFAULTS_RELEASE)
    assert server, f"RemoteMCPServer {DEFAULTS_RELEASE} was not rendered"
    assert server["metadata"]["labels"][DISCOVERY_LABEL] == "disabled"
    assert "headersFrom" not in server["spec"], server["spec"]
    assert_server_accepted(server)
