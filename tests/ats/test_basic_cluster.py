import logging
import os

import pytest
from pykube.objects import object_factory
from pytest_helm_charts.clusters import Cluster

logger = logging.getLogger(__name__)


@pytest.mark.smoke
def test_agent_cr_created(kube_cluster: Cluster) -> None:
    """Smoke test: installing the chart on kind yields exactly one Agent CR.

    The chart's entire job is to render a single kagent Agent custom
    resource, so the smoke signal is that the release's Agent exists and was
    accepted by the real kagent CRD schema (bootstrapped onto the kind
    cluster via `cluster-crds` in .ats/main.yaml). No kagent controller runs
    here -- acceptance by the API server is the assertion, not
    reconciliation.
    """
    release_name = os.environ["ATS_RELEASE_NAME"]
    namespace = os.environ.get("ATS_RELEASE_NAMESPACE", "default")

    Agent = object_factory(kube_cluster.kube_client, "kagent.dev/v1alpha2", "Agent")
    agents = list(Agent.objects(kube_cluster.kube_client, namespace=namespace))
    assert len(agents) == 1

    agent = agents[0]
    # agent.name defaults to the release name; one release == one Agent.
    assert agent.name == release_name
    assert agent.labels["app.kubernetes.io/instance"] == release_name
    assert agent.obj["spec"]["type"] == "Declarative"
