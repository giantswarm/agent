"""Functional: the readiness wait fails fast, with the reason.

Three shapes an operator gets wrong, each against the runtime the smoke
brought up, each answered in seconds instead of the Ready timeout:

  * a template no Harness admits — `agent.harness` names a Harness that does
    not exist, so the admission label matches no selector; the controller
    catches up with the generation and reports no Harness;
  * a Harness on a WorkerPool without a ready worker — a pool whose worker
    image does not exist never gets a worker, and a template admitted by a
    Harness on that pool never boots;
  * a Harness whose image cannot be pulled — a digest the registry has never
    seen. The golden boot's pull fails inside the worker with the registry's
    answer; Substrate crashes the golden actor on it and records the cause on
    the template (`GoldenActorCrashed: actor … crashed: … MANIFEST_UNKNOWN`),
    which kagent reports as `Ready=False ActorTemplateFailed` with that
    message. The wait fails on it the moment it is reported.

The wait ends at once on any failed golden boot (`Ready=False
ActorTemplateFailed`, Substrate's own message: an invalid golden actor, a
crash before the snapshot, an unexpected state).

The Harnesses and the WorkerPool of these cases are the test's own objects,
named after the case, and are removed with the releases.
"""

import logging
import time
from typing import Any, Callable, Dict, Iterator

import pytest

from conftest import BOOT_TIMEOUT_S, KAGENT_NAMESPACE, UNADMITTED_TIMEOUT_S, FailFast, Kube, harness_object, wait_template_ready

logger = logging.getLogger(__name__)

UNADMITTED = "ats-unadmitted"
NO_WORKERS = "ats-no-workers"
UNPULLABLE = "ats-unpullable-image"
MISSING_WORKER_IMAGE = "ghcr.io/giantswarm/substrate/ateom-gvisor:0.0.0-does-not-exist"
# A digest the registry has never seen, in a repository that exists: the
# Harness CRD accepts no tag, and the pull is answered 404 (MANIFEST_UNKNOWN).
MISSING_HARNESS_IMAGE = "ghcr.io/giantswarm/kagent/golang-adk@sha256:" + "0" * 64


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


@pytest.mark.functional
def test_unpullable_harness_image_fails_fast(kube: Kube, release: Callable[..., None], own_objects: Callable[[Dict[str, Any]], None]) -> None:
    own_objects(harness_object(UNPULLABLE, image=MISSING_HARNESS_IMAGE))
    release(UNPULLABLE, sets=[f"agent.harness={UNPULLABLE}"])
    started = time.monotonic()
    with pytest.raises(FailFast, match="ActorTemplateFailed") as failure:
        wait_template_ready(kube, UNPULLABLE, harness=UNPULLABLE, timeout=BOOT_TIMEOUT_S)
    elapsed = time.monotonic() - started
    logger.info("fail-fast after %.0fs: %s", elapsed, failure.value)
    # Substrate crashed the golden actor on the registry's answer and recorded
    # the cause; kagent carries it in the Ready condition's message.
    assert "GoldenActorCrashed" in str(failure.value)
    assert elapsed < BOOT_TIMEOUT_S
