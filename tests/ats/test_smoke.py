"""Smoke: the chart installed on kind yields the agent's AgentTemplate and its
muster RemoteMCPServer, both accepted by the kagent.dev/v1alpha3 CRDs.

ATS deploys the chart with tests/ats/values-smoke.yaml before this runs
(.ats/main.yaml). No kagent controller runs on the kind cluster: acceptance by
the API server is the assertion, not reconciliation — the Ready proof on the
platform Harness is a separate step (giantswarm/agent#26).

Written against the ATS 1.x contract (cluster-crds option, ATS_RELEASE_* env
vars, docs/TEST_CONTRACT.md in giantswarm/app-test-suite).
"""

import logging
import os

import pytest
from pykube.objects import object_factory
from pytest_helm_charts.clusters import Cluster

from conftest import API_VERSION, HARNESS_LABEL, TOOLSET_HEADER

logger = logging.getLogger(__name__)


@pytest.mark.smoke
def test_agenttemplate_and_remotemcpserver_accepted(kube_cluster: Cluster) -> None:
    release_name = os.environ["ATS_RELEASE_NAME"]
    namespace = os.environ.get("ATS_RELEASE_NAMESPACE", "default")
    client = kube_cluster.kube_client

    AgentTemplate = object_factory(client, API_VERSION, "AgentTemplate")
    RemoteMCPServer = object_factory(client, API_VERSION, "RemoteMCPServer")
    templates = list(AgentTemplate.objects(client, namespace=namespace))
    servers = list(RemoteMCPServer.objects(client, namespace=namespace))
    assert len(templates) == 1, [t.name for t in templates]
    assert len(servers) == 1, [s.name for s in servers]

    template, server = templates[0], servers[0]
    # agent.name defaults to the release name; both objects carry it.
    assert template.name == release_name
    assert server.name == release_name

    # The AgentTemplate: the Harness admission label, the ui annotations, the
    # extra labels/annotations, the field mapping of values-smoke.yaml.
    assert template.labels[HARNESS_LABEL] == "kagent"
    assert template.labels["app.kubernetes.io/instance"] == release_name
    assert template.labels["giantswarm.io/owner"] == "ats"
    assert template.annotations["ui.giantswarm.io/display-name"] == "ATS Smoke Agent"
    assert template.annotations["ui.giantswarm.io/icon-url"] == "https://avatars.example.com/ats-smoke.svg"
    assert template.annotations["giantswarm.io/scenario"] == "smoke"
    spec = template.obj["spec"]
    assert spec["modelConfig"] == {"name": "default-model-config"}
    assert spec["description"] == "Exercises the chart's field mapping against the v1alpha3 CRDs."
    assert spec["systemPrompt"] == "You are the chart's smoke test. Be brief."
    assert spec["skills"] == [
        {
            "name": "agent-self-awareness",
            "source": {
                "git": {
                    "url": "https://github.com/giantswarm/agent-skills",
                    "commit": "cb1fb768bbbbcaa035b884a99ad308b14f846468",
                },
                "path": "agent-self-awareness",
            },
        },
        {
            "name": "runbooks",
            "source": {
                "oci": "registry.example.io/skills/runbooks@sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        },
    ]
    assert spec["tools"][0]["mcp"]["server"] == {"kind": "RemoteMCPServer", "name": release_name}
    assert spec["tools"][0]["mcp"]["tools"] == ["list_tools", "call_tool"]
    assert spec["tools"][1]["mcp"] == {"server": {"kind": "RemoteMCPServer", "name": "github"}, "requireApproval": True}
    assert len(spec["tools"]) == 2

    # The RemoteMCPServer: muster's URL, the toolset header, never an
    # Authorization header, the discovery opt-out, the shared labels.
    assert server.labels["kagent.dev/discovery"] == "disabled"
    assert server.labels["app.kubernetes.io/instance"] == release_name
    assert server.labels["giantswarm.io/owner"] == "ats"
    assert HARNESS_LABEL not in server.labels
    spec = server.obj["spec"]
    assert spec["url"] == "http://muster.agent-platform.svc.cluster.local:8090/mcp"
    assert spec["protocol"] == "STREAMABLE_HTTP"
    assert spec["headersFrom"] == [{"name": TOOLSET_HEADER, "value": "preset:read-only,server:mcp-kubernetes"}]
    assert not [h for h in spec["headersFrom"] if h["name"].lower() == "authorization"]
    logger.info("%s and %s accepted at %s", template.name, server.name, API_VERSION)
