"""Functional: the readiness wait fails fast, with the reason.

Two shapes an operator gets wrong, each against the runtime the smoke
brought up, each answered in seconds instead of the Ready timeout:

  * a template no Harness admits — `agent.harness` names a Harness that does
    not exist, so the admission label matches no selector; the controller
    catches up with the generation and reports no Harness;
  * a Harness on a WorkerPool without a ready worker — a pool whose worker
    image does not exist never gets a worker, and a template admitted by a
    Harness on that pool never boots.

The wait also ends at once on a failed golden boot (`Ready=False
ActorTemplateFailed`, Substrate's own message: an invalid golden actor, a
crash before the snapshot, an unexpected state). A Harness image that cannot
be pulled is NOT such a case on the pinned Substrate: the golden actor's
resume fails inside the worker and ate-api-server's ActorTemplate reconciler
retries a resume error with backoff instead of recording it, so kagent keeps
reporting `ActorTemplatePending` (measured 2026-09-11 on substrate 0.0.27-gs.2
+ kagent 0.11.0-gs.3: a Harness on `golang-adk@sha256:000…0` stayed pending
for the whole 300 s budget, no error message). The wait would fail fast the
moment Substrate reports it; until then that case is not asserted here.

The Harnesses and the WorkerPool of these cases are the test's own objects,
named after the case, and are removed with the releases.
"""

import logging
from typing import Any, Callable, Dict, Iterator

import pytest

from conftest import BOOT_TIMEOUT_S, KAGENT_NAMESPACE, UNADMITTED_TIMEOUT_S, FailFast, Kube, harness_object, wait_template_ready

logger = logging.getLogger(__name__)

UNADMITTED = "ats-unadmitted"
NO_WORKERS = "ats-no-workers"
MISSING_WORKER_IMAGE = "ghcr.io/giantswarm/substrate/ateom-gvisor:0.0.0-does-not-exist"


@pytest.fixture
def own_objects(kube: Kube, runtime: None) -> Iterator[Callable[[Dict[str, Any]], None]]:
    """Applies the case's Harness/WorkerPool objects and deletes them afterwards."""
    applied = []

    def apply(obj: Dict[str, Any]) -> None:
        kube.apply(obj)
        applied.append(obj)

    yield apply
    for obj in reversed(applied):
        kube.delete(obj["kind"].lower(), obj["metadata"]["name"], namespace=obj["metadata"]["namespace"])


@pytest.mark.functional
def test_unadmitted_template_fails_fast(kube: Kube, release: Callable[..., None]) -> None:
    release(UNADMITTED, sets=[f"agent.harness={UNADMITTED}"])
    with pytest.raises(FailFast, match="no Harness admits") as failure:
        wait_template_ready(kube, UNADMITTED, harness=UNADMITTED, timeout=UNADMITTED_TIMEOUT_S)
    logger.info("fail-fast: %s", failure.value)
    # The controller did evaluate the template: it caught up with the generation and reports no Harness.
    template = kube.get("agenttemplates.kagent.dev", UNADMITTED, namespace=KAGENT_NAMESPACE)
    assert template
    assert template["status"]["observedGeneration"] == template["metadata"]["generation"]
    assert not template["status"].get("harnesses")


@pytest.mark.functional
def test_worker_pool_without_a_ready_worker_fails_fast(kube: Kube, release: Callable[..., None], own_objects: Callable[[Dict[str, Any]], None]) -> None:
    own_objects({
        "apiVersion": "ate.dev/v1alpha1",
        "kind": "WorkerPool",
        "metadata": {"name": NO_WORKERS, "namespace": KAGENT_NAMESPACE},
        "spec": {"replicas": 1, "workerImage": MISSING_WORKER_IMAGE, "sandboxClass": "gvisor"},
    })
    own_objects(harness_object(NO_WORKERS, worker_pool=NO_WORKERS))
    release(NO_WORKERS, sets=[f"agent.harness={NO_WORKERS}"])
    with pytest.raises(FailFast, match="no ready worker") as failure:
        wait_template_ready(kube, NO_WORKERS, harness=NO_WORKERS, timeout=BOOT_TIMEOUT_S)
    logger.info("fail-fast: %s", failure.value)
