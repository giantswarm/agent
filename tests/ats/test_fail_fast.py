"""Functional: the readiness wait fails fast, with the reason.

Three shapes an operator gets wrong, each against the runtime the smoke
brought up, each answered in seconds instead of the Ready timeout:

  * an Agent whose Harness does not exist — `agent.harness` names a Harness
    that is not in the namespace; the controller reports ResolvedRefs=False
    ReferenceResolutionFailed and the Agent recovers when the Harness appears;
  * a Harness on a WorkerPool without a ready worker — a pool whose pod
    template selects a node that does not exist never gets a worker, and an
    Agent on a Harness on that pool never boots. (A gVisor pool's
    `spec.workerImage` is not the lever: ate-controller runs every gVisor pool
    on the release's own `ateom-gvisor`, so a bogus image still gets a worker.)
  * a Harness whose image cannot be pulled — a digest the registry has never
    seen. The golden boot's pull fails inside the worker with the registry's
    answer; Substrate crashes the golden actor on it and records the cause on
    the Agent (`GoldenActorCrashed: actor … crashed: … MANIFEST_UNKNOWN`). The
    controller cannot tell a refused pull from a transient one, so it reports
    `Ready=False ActorTemplateRetrying` with that message and starts the boot
    over, six boots in all before `ActorTemplateFailed`. The reason is on the
    Agent after the first boot, seconds in; the test asserts that and does not
    sit out the budget.

The wait ends at once on a golden boot the controller gave up on (`Ready=False
ActorTemplateFailed`, Substrate's own message: an invalid golden actor, a
budget spent on a crash before the snapshot, an unexpected state).

The Harnesses and the WorkerPool of these cases are the test's own objects,
named after the case, and are removed with the releases.
"""

import logging
import time
from typing import Any, Callable, Dict, Iterator

import pytest

from conftest import AGENTS, BOOT_TIMEOUT_S, KAGENT_NAMESPACE, MISSING_HARNESS_TIMEOUT_S, WORKER_IMAGE, FailFast, Kube, condition, describe, harness_object, wait_agent_ready, wait_for

logger = logging.getLogger(__name__)

MISSING_HARNESS = "ats-missing-harness"
NO_WORKERS = "ats-no-workers"
UNPULLABLE = "ats-unpullable-image"
# A node label no node carries: the pool's worker stays Pending.
NO_SUCH_NODE = {"ats.giantswarm.io/no-such-node": "true"}
# A digest the registry has never seen, in a repository that exists: the
# Harness CRD accepts no tag, and the pull is answered 404 (MANIFEST_UNKNOWN).
MISSING_HARNESS_IMAGE = "gsoci.azurecr.io/giantswarm/kagent/golang-adk@sha256:" + "0" * 64


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
def test_missing_harness_fails_fast(kube: Kube, release: Callable[..., None]) -> None:
    release(MISSING_HARNESS, sets=[f"agent.harness={MISSING_HARNESS}"])
    with pytest.raises(FailFast, match="ResolvedRefs=False ReferenceResolutionFailed") as failure:
        wait_agent_ready(kube, MISSING_HARNESS, timeout=MISSING_HARNESS_TIMEOUT_S)
    logger.info("fail-fast: %s", failure.value)
    # The controller did evaluate the Agent: it caught up with the generation and never became Ready.
    agent = kube.get(AGENTS, MISSING_HARNESS, namespace=KAGENT_NAMESPACE)
    assert agent
    assert agent["status"]["observedGeneration"] == agent["metadata"]["generation"]
    assert not agent["status"].get("latestSuccessfulRevision")


@pytest.mark.functional
def test_worker_pool_without_a_ready_worker_fails_fast(kube: Kube, release: Callable[..., None], own_objects: Callable[[Dict[str, Any]], None]) -> None:
    own_objects({
        "apiVersion": "ate.dev/v1alpha1",
        "kind": "WorkerPool",
        "metadata": {"name": NO_WORKERS, "namespace": KAGENT_NAMESPACE},
        "spec": {"replicas": 1, "workerImage": WORKER_IMAGE, "sandboxClass": "gvisor", "template": {"nodeSelector": NO_SUCH_NODE}},
    })
    own_objects(harness_object(NO_WORKERS, worker_pool=NO_WORKERS))
    release(NO_WORKERS, sets=[f"agent.harness={NO_WORKERS}"])
    with pytest.raises(FailFast, match="no ready worker") as failure:
        wait_agent_ready(kube, NO_WORKERS, timeout=BOOT_TIMEOUT_S)
    logger.info("fail-fast: %s", failure.value)


@pytest.mark.functional
def test_unpullable_harness_image_reports_the_registry_answer(kube: Kube, release: Callable[..., None], own_objects: Callable[[Dict[str, Any]], None]) -> None:
    own_objects(harness_object(UNPULLABLE, image=MISSING_HARNESS_IMAGE))
    release(UNPULLABLE, sets=[f"agent.harness={UNPULLABLE}"])
    started = time.monotonic()

    def retrying() -> Any:
        agent = kube.get(AGENTS, UNPULLABLE, namespace=KAGENT_NAMESPACE) or {}
        ready = condition(agent.get("status") or {}, "Ready")
        if ready.get("status") == "False" and ready.get("reason") == "ActorTemplateRetrying":
            return describe(ready)
        logger.info("%s: %s", UNPULLABLE, describe(ready) if ready else "no Ready condition yet")
        return None

    reported = wait_for(f"Agent {UNPULLABLE} retrying its golden boot", retrying, BOOT_TIMEOUT_S)
    elapsed = time.monotonic() - started
    logger.info("registry answer on the Agent after %.0fs: %s", elapsed, reported)
    # Substrate crashed the golden actor on the registry's answer and recorded
    # the cause; kagent carries it in the Ready condition's message, with the
    # attempt's place in the budget.
    assert "GoldenActorCrashed" in reported
    assert "MANIFEST_UNKNOWN" in reported
    assert "golden boot 1 of 6 failed" in reported
    assert elapsed < BOOT_TIMEOUT_S
