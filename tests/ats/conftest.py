"""The ATS scenarios of the agent chart run on the platform's real runtime.

The generated CI job (execute-chart-tests) creates the kind cluster from
.ats/kind-config.yaml — Kubernetes 1.35+, the ClusterTrustBundle,
ClusterTrustBundleProjection and PodCertificateRequest gates and the
certificates.k8s.io/v1beta1 API — and ATS applies the kagent and Substrate
CRDs (.ats/main.yaml cluster-crds) before anything else. ATS deploys nothing
itself (app-tests-skip-app-deploy): the runtime has to be up BEFORE a release of
this chart, so the ``runtime`` fixture brings it up, in this order, idempotent:

  1. the preflight — the apiserver serves certificates.k8s.io/v1beta1 (a
     cluster without the gates fails here, with the reason, instead of at the
     first worker pod);
  2. the Agent Substrate bootstrap the substrate chart mounts but does not
     render (substrate-bootstrap.yaml, a Job: the CA pools the
     podcertificate-controller signs from, the JWT authority and CA pool
     ate-api-server mints actor identities from, the derived trust anchor and
     ate-api-server's authentication config), then the substrate chart of the
     Giant Swarm line into ate-system with its bundled database and snapshot
     store (values-substrate.yaml);
  3. the kagent chart of the Giant Swarm line into the kagent namespace with
     Substrate wiring, its WorkerPool of gVisor workers, the bundled database,
     the default ModelConfig with a placeholder provider key and no UI
     (values-kagent.yaml);
  4. the platform Harness — the Go ADK runtime image by digest, the WorkerPool,
     the snapshot location and the admission selector that is the chart's
     whole contract with the platform: label
     agent-platform.giantswarm.io/harness=<Harness name>.

A release of this chart then reaches Ready when its AgentTemplate is admitted
by that Harness, compiled, and booted once into a golden snapshot on a worker
(status.harnesses[] for the Harness: Accepted, ResolvedRefs, Compatible and
Ready True for the current generation). No model is called: Ready means
compiled, admitted and bootable. ``wait_template_ready`` is the one wait, and it
fails fast with the controller's or Substrate's reason instead of sitting out
the timeout: no Harness admits the template (the controller caught up with the
generation and reports no Harness), a reference or compatibility failure, a
golden boot Substrate reports as failed (Ready=False ActorTemplateFailed with
its message — a Harness image the registry refuses crashes the golden actor
with the registry's answer, test_fail_fast.py asserts it), or a WorkerPool
with no ready worker.

Pins. The two lines are named once each below (KAGENT_LINE, SUBSTRATE_LINE);
the Harness image is the Go ADK image of the kagent line's release BY DIGEST
(the Harness CRD accepts no tag). The CRDs come from the same tags through
.ats/main.yaml (cluster-crds), and the runtime fixture refuses to start when
the two disagree, so a half-done bump is caught before anything is installed.
The bump procedure is in .ats/main.yaml.

ATS runs `uv run pytest -m smoke` then `-m functional` in this directory on the
one cluster, with KUBECONFIG, ATS_CHART_PATH and ATS_CHART_VERSION set
(docs/TEST_CONTRACT.md in giantswarm/app-test-suite). Local run against a kind
cluster created with .ats/kind-config.yaml:

  helm package helm/agent --version 1.99.0-dev.local -d dist
  cd tests/ats && KUBECONFIG=… ATS_CLUSTER_TYPE=kind \\
    ATS_CHART_PATH=$PWD/../../dist/agent-1.99.0-dev.local.tgz ATS_CHART_VERSION=1.99.0-dev.local \\
    uv run pytest -m smoke --log-cli-level info
"""

import json
import logging
import subprocess  # nosec: fixed argv throughout; the archive path comes from ATS
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
import yaml
from pytest_helm_charts.clusters import Cluster

logger = logging.getLogger(__name__)

ATS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ATS_DIR.parents[1]
ATS_CONFIG = REPO_ROOT / ".ats" / "main.yaml"

# ---------------------------------------------------------------------------
# The contract the chart renders (giantswarm/agent#25) and the platform reads.
# ---------------------------------------------------------------------------

API_VERSION = "kagent.dev/v1alpha3"
HARNESS_LABEL = "agent-platform.giantswarm.io/harness"
TOOLSET_HEADER = "X-Muster-Toolset"
DISCOVERY_LABEL = "kagent.dev/discovery"

# ---------------------------------------------------------------------------
# Pins — the two lines the runtime comes from. Bump procedure: .ats/main.yaml.
# ---------------------------------------------------------------------------

# The kagent line (giantswarm/kagent-upstream), a release tag `vX.Y.Z-gs.N`
# without the `v`: the kagent chart and the controller image carry this version.
KAGENT_LINE = "0.11.0-gs.3"
KAGENT_CHARTS = "oci://ghcr.io/giantswarm/kagent/helm"
# The Go ADK runtime image of that release, by digest — the image index digest
# `crane digest ghcr.io/giantswarm/kagent/golang-adk:<KAGENT_LINE>` reports
# (builds.md on the fork's `ledger` branch lists it too, column golang-adk).
HARNESS_IMAGE = "ghcr.io/giantswarm/kagent/golang-adk@sha256:a2d23f5eb9c01e1903459a6e742f7d4aaa5e950d7e9aa6f07f8982761be0163a"
# The Substrate line (giantswarm/substrate), a release tag without the `v`: the
# substrate chart, its control-plane images and the gVisor worker image.
SUBSTRATE_LINE = "0.0.27-gs.4"
SUBSTRATE_CHARTS = "oci://ghcr.io/giantswarm/substrate/helm"
WORKER_IMAGE = f"ghcr.io/giantswarm/substrate/ateom-gvisor:{SUBSTRATE_LINE}"

# ---------------------------------------------------------------------------
# The runtime's shape (the meta chart's names: agent-platform 4.x).
# ---------------------------------------------------------------------------

SUBSTRATE_NAMESPACE = "ate-system"
PODCERT_NAMESPACE = "podcertificate-controller-system"
SUBSTRATE_RELEASE = "substrate"
KAGENT_NAMESPACE = "kagent"
KAGENT_RELEASE = "kagent"
HARNESS = "kagent"
WORKER_POOL = "kagent-default"
MODEL_CONFIG = "default-model-config"
SNAPSHOT_LOCATION = "s3://ate-snapshots/kagent"
SANDBOX_CONFIG = "gvisor-default"

BOOTSTRAP_MANIFEST = ATS_DIR / "substrate-bootstrap.yaml"
BOOTSTRAP_JOB = "substrate-bootstrap"
SUBSTRATE_VALUES = ATS_DIR / "values-substrate.yaml"
KAGENT_VALUES = ATS_DIR / "values-kagent.yaml"

# Budgets. The runtime comes up once per cluster (the functional scenario finds
# it installed); a golden boot pulls the Go ADK image into the worker the first
# time, later boots find it cached.
INSTALL_TIMEOUT = "10m"
BOOTSTRAP_TIMEOUT_S = 300
WORKER_POOL_TIMEOUT_S = 420
FIRST_BOOT_TIMEOUT_S = 600
BOOT_TIMEOUT_S = 300
# The discovery reconciler's pass over a RemoteMCPServer it does not connect to.
SERVER_TIMEOUT_S = 120
# A WorkerPool without a ready worker for this long is a failure, not a restart.
NO_READY_WORKER_GRACE_S = 45
# The controller's pass over a template that no Harness admits is seconds; an
# unadmitted template still without a status after this long is a controller
# problem, reported as such.
UNADMITTED_TIMEOUT_S = 120

# Terminal Ready reasons: the controller will not retry these on its own.
# ActorTemplatePending is the golden boot still running.
READY_PENDING_REASON = "ActorTemplatePending"


class FailFast(AssertionError):
    """A readiness wait that ended early with a reason (never retried)."""


# ---------------------------------------------------------------------------
# Processes, waiting, timing
# ---------------------------------------------------------------------------


def run(args: List[str], timeout: int = 900, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(args))
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, input=stdin)  # nosec


def wait_for(what: str, predicate: Callable[[], Any], timeout: float, interval: float = 5) -> Any:
    """Poll until ``predicate`` returns a truthy value (returned) or the
    timeout passes (AssertionError naming the last outcome). Exceptions inside
    the predicate count as "not yet" — except a FailFast, which is the answer."""
    deadline = time.monotonic() + timeout
    last: Any = "not evaluated"
    while True:
        try:
            value = predicate()
            if value:
                return value
            last = value
        except FailFast:
            raise
        except Exception as exc:  # the predicate reads a cluster that is still converging
            last = f"{type(exc).__name__}: {exc}"
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out after {timeout:.0f}s waiting for {what}; last: {str(last)[:600]}")
        time.sleep(interval)


class Timings:
    """Wall-clock seconds per phase, logged so the CI log carries the budget."""

    def __init__(self) -> None:
        self.entries: Dict[str, float] = {}

    def record(self, phase: str, seconds: float) -> None:
        self.entries[phase] = seconds
        logger.info("TIMING %s: %.0f s", phase, seconds)


TIMINGS = Timings()


# ---------------------------------------------------------------------------
# kubectl and helm (both come with the ATS image)
# ---------------------------------------------------------------------------


class Kube:
    """kubectl against the ATS cluster, JSON in and out."""

    def __init__(self, kubeconfig: str) -> None:
        self.kubeconfig = kubeconfig

    def cmd(self, args: List[str], stdin: Optional[str] = None, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
        r = run(["kubectl", "--kubeconfig", self.kubeconfig, *args], timeout=timeout, stdin=stdin)
        if check and r.returncode != 0:
            raise AssertionError(f"kubectl {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def get(self, *args: str, namespace: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """One object, or None when it does not exist."""
        ns = ["-n", namespace] if namespace else []
        r = self.cmd(["get", *ns, *args, "-o", "json", "--ignore-not-found"])
        return json.loads(r.stdout) if r.stdout.strip() else None

    def items(self, *args: str, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        ns = ["-n", namespace] if namespace else []
        r = self.cmd(["get", *ns, *args, "-o", "json", "--ignore-not-found"])
        if not r.stdout.strip():
            return []
        out = json.loads(r.stdout)
        return out.get("items", [out]) if isinstance(out, dict) else out

    def apply(self, manifest: Any) -> None:
        text = manifest if isinstance(manifest, str) else yaml.safe_dump_all(manifest) if isinstance(manifest, list) else yaml.safe_dump(manifest)
        self.cmd(["apply", "-f", "-"], stdin=text)

    def delete(self, *args: str, namespace: Optional[str] = None, timeout: str = "3m") -> None:
        ns = ["-n", namespace] if namespace else []
        self.cmd(["delete", *ns, *args, "--ignore-not-found", "--wait=true", f"--timeout={timeout}"])

    def raw(self, path: str) -> subprocess.CompletedProcess:
        return self.cmd(["get", "--raw", path], check=False, timeout=60)

    def ensure_namespace(self, name: str) -> None:
        self.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}})

    def pods_summary(self, namespace: str, selector: Optional[str] = None) -> str:
        """One line per pod: phase and the waiting reason of every container."""
        sel = ["-l", selector] if selector else []
        lines = []
        for pod in self.items("pods", *sel, namespace=namespace):
            waits = [
                f"{c['name']}={c['state']['waiting'].get('reason', 'Waiting')}"
                for c in pod.get("status", {}).get("containerStatuses", []) or []
                if "waiting" in c.get("state", {})
            ]
            lines.append(f"{pod['metadata']['name']} {pod.get('status', {}).get('phase', '?')} {' '.join(waits)}".rstrip())
        return "; ".join(lines) or "no pods"

    def dump(self, commands: List[str]) -> None:
        """Best-effort state dump when something fails, so the CI log explains itself."""
        for c in commands:
            r = self.cmd(c.split(" "), check=False, timeout=120)
            logger.error("$ kubectl %s\n%s%s", c, r.stdout[-8000:], r.stderr[-2000:])


class Helm:
    def __init__(self, kubeconfig: str) -> None:
        self.kubeconfig = kubeconfig

    def _run(self, *args: str, timeout: int = 20 * 60) -> subprocess.CompletedProcess:
        return run(["helm", "--kubeconfig", self.kubeconfig, *args], timeout=timeout)

    def install(
        self,
        release: str,
        chart: str,
        namespace: str,
        values: Optional[List[Path]] = None,
        sets: Optional[List[str]] = None,
        version: Optional[str] = None,
        wait: bool = True,
        timeout: str = INSTALL_TIMEOUT,
        take_ownership: bool = False,
    ) -> float:
        """`helm upgrade --install`; returns the wall-clock seconds, fails the
        test with Helm's output when the install fails."""
        args = ["upgrade", "--install", release, chart, "--namespace", namespace, "--create-namespace", "--timeout", timeout]
        if version:
            args += ["--version", version]
        for v in values or []:
            args += ["--values", str(v)]
        for s in sets or []:
            args += ["--set", s]
        if wait:
            args.append("--wait")
        if take_ownership:
            args.append("--take-ownership")
        started = time.monotonic()
        r = self._run(*args)
        elapsed = time.monotonic() - started
        assert r.returncode == 0, f"helm upgrade --install {release} failed after {elapsed:.0f}s:\n{r.stdout}\n{r.stderr}"
        logger.info("helm upgrade --install %s%s returned after %.0f s", release, " --wait" if wait else "", elapsed)
        return elapsed

    def uninstall(self, release: str, namespace: str) -> None:
        r = self._run("uninstall", release, "--namespace", namespace, "--wait", "--timeout", "5m", timeout=10 * 60)
        if r.returncode != 0 and "not found" not in r.stderr:
            raise AssertionError(f"helm uninstall {release} failed:\n{r.stdout}\n{r.stderr}")

    def deployed_version(self, release: str, namespace: str) -> Optional[str]:
        """The chart version of a deployed release, None when there is none."""
        r = self._run("list", "--namespace", namespace, "--deployed", "-o", "json", "--filter", f"^{release}$", timeout=120)
        assert r.returncode == 0, r.stderr
        for entry in json.loads(r.stdout or "[]"):
            if entry.get("name") == release:
                return str(entry.get("chart", "")).rsplit("-", 1)[-1]
        return None


# ---------------------------------------------------------------------------
# The runtime: Substrate, kagent, the platform Harness
# ---------------------------------------------------------------------------


def assert_pins_match_ats_config() -> None:
    """The CRDs ATS applied (cluster-crds in .ats/main.yaml) come from the same
    tags as the charts this file installs — a half-done bump stops here."""
    config = yaml.safe_load(ATS_CONFIG.read_text(encoding="utf-8")) or {}
    crds = str(config.get("cluster-crds", ""))
    for line, marker in ((KAGENT_LINE, f"kagent-upstream/v{KAGENT_LINE}/"), (SUBSTRATE_LINE, f"substrate/v{SUBSTRATE_LINE}/")):
        assert marker in crds, (
            f"pin mismatch: tests/ats/conftest.py pins {line} but .ats/main.yaml cluster-crds does not carry {marker!r}"
            " — bump both (the procedure is in .ats/main.yaml)"
        )


def preflight(kube: Kube) -> None:
    """The cluster runs the gates Substrate needs (.ats/kind-config.yaml). A
    cluster created without them can only be recreated, so say so first."""
    r = kube.raw("/apis/certificates.k8s.io/v1beta1")
    assert r.returncode == 0, (
        "the apiserver does not serve certificates.k8s.io/v1beta1: Substrate needs the PodCertificateRequest and"
        " ClusterTrustBundle feature gates and that API (.ats/kind-config.yaml), and feature gates are fixed at"
        f" `kind create cluster`; the CI job passes the file via kind_config. kubectl said:\n{r.stderr}"
    )
    version = json.loads(kube.cmd(["version", "-o", "json"]).stdout)["serverVersion"]
    minor = int("".join(ch for ch in version["minor"] if ch.isdigit()) or 0)
    assert (int(version["major"]), minor) >= (1, 35), f"Kubernetes {version['gitVersion']} is older than 1.35, which the v1beta1 certificates API needs"
    logger.info("preflight ok: Kubernetes %s serves certificates.k8s.io/v1beta1", version["gitVersion"])


def bootstrap_substrate(kube: Kube) -> None:
    """The CA/JWT pools, the trust anchor and ate-api-server's authentication
    config (substrate-bootstrap.yaml). Idempotent: an existing pool is kept."""
    for ns in (SUBSTRATE_NAMESPACE, PODCERT_NAMESPACE):
        kube.ensure_namespace(ns)
    kube.cmd(["apply", "-f", str(BOOTSTRAP_MANIFEST)])
    r = kube.cmd(["-n", SUBSTRATE_NAMESPACE, "wait", "--for=condition=complete", f"--timeout={BOOTSTRAP_TIMEOUT_S}s", f"job/{BOOTSTRAP_JOB}"], check=False)
    if r.returncode != 0:
        kube.dump([f"-n {SUBSTRATE_NAMESPACE} get job {BOOTSTRAP_JOB} -o yaml", f"-n {SUBSTRATE_NAMESPACE} logs job/{BOOTSTRAP_JOB} --all-containers --tail=100",
                   f"-n {SUBSTRATE_NAMESPACE} get events --sort-by=.lastTimestamp"])
        raise AssertionError(f"the Substrate bootstrap Job did not complete within {BOOTSTRAP_TIMEOUT_S}s:\n{r.stdout}\n{r.stderr}")
    logger.info("bootstrap: %s", kube.cmd(["-n", SUBSTRATE_NAMESPACE, "logs", f"job/{BOOTSTRAP_JOB}", "-c", "kubectl", "--tail=20"], check=False).stdout.strip())


def install_substrate(kube: Kube, helm: Helm) -> None:
    if helm.deployed_version(SUBSTRATE_RELEASE, SUBSTRATE_NAMESPACE) == SUBSTRATE_LINE:
        logger.info("substrate %s already deployed in %s", SUBSTRATE_LINE, SUBSTRATE_NAMESPACE)
        return
    started = time.monotonic()
    try:
        # --take-ownership: the chart renders the podcertificate-controller-system
        # Namespace the bootstrap had to create first (the pools live in it).
        helm.install(SUBSTRATE_RELEASE, f"{SUBSTRATE_CHARTS}/substrate", SUBSTRATE_NAMESPACE, values=[SUBSTRATE_VALUES], version=SUBSTRATE_LINE, take_ownership=True)
    except AssertionError:
        dump_substrate(kube)
        raise
    TIMINGS.record(f"substrate {SUBSTRATE_LINE} installed (ate-api-server, ate-controller, atelet, atenet, postgres, rustfs)", time.monotonic() - started)
    assert kube.get("sandboxconfigs.ate.dev", SANDBOX_CONFIG), f"substrate installed but SandboxConfig {SANDBOX_CONFIG} is missing; WorkerPools name it"


def install_kagent(kube: Kube, helm: Helm) -> None:
    if helm.deployed_version(KAGENT_RELEASE, KAGENT_NAMESPACE) == KAGENT_LINE:
        logger.info("kagent %s already deployed in %s", KAGENT_LINE, KAGENT_NAMESPACE)
        return
    started = time.monotonic()
    try:
        helm.install(KAGENT_RELEASE, f"{KAGENT_CHARTS}/kagent", KAGENT_NAMESPACE, values=[KAGENT_VALUES],
                     sets=[f"substrateWorkerPool.workerImage={WORKER_IMAGE}"], version=KAGENT_LINE)
    except AssertionError:
        dump_kagent(kube)
        raise
    TIMINGS.record(f"kagent {KAGENT_LINE} installed (controller, bundled postgres, WorkerPool {WORKER_POOL})", time.monotonic() - started)


def worker_pool_ready(kube: Kube, name: str, namespace: str = KAGENT_NAMESPACE) -> int:
    pool = kube.get("workerpools.ate.dev", name, namespace=namespace)
    assert pool, f"WorkerPool {namespace}/{name} does not exist"
    return int((pool.get("status") or {}).get("readyReplicas") or 0)


def no_ready_worker_reason(kube: Kube, pool: str, namespace: str = KAGENT_NAMESPACE) -> str:
    return f"WorkerPool {namespace}/{pool} has no ready worker: {kube.pods_summary(namespace, f'ate.dev/worker-pool={pool}')}"


def wait_worker_pool(kube: Kube, name: str = WORKER_POOL, timeout: float = WORKER_POOL_TIMEOUT_S) -> None:
    """At least one ready gVisor worker, or the pool's pods' state as the reason."""
    started = time.monotonic()
    try:
        wait_for(f"WorkerPool {name} with a ready worker", lambda: worker_pool_ready(kube, name) >= 1, timeout, interval=10)
    except AssertionError as exc:
        dump_kagent(kube)
        dump_substrate(kube)
        raise FailFast(f"{no_ready_worker_reason(kube, name)} ({exc})") from exc
    TIMINGS.record(f"WorkerPool {name}: first worker ready", time.monotonic() - started)


def harness_object(name: str, image: str = HARNESS_IMAGE, worker_pool: str = WORKER_POOL, namespace: str = KAGENT_NAMESPACE) -> Dict[str, Any]:
    """The platform Harness (what the connectivity chart of agent-platform 4.x
    renders): one label is the whole admission contract."""
    return {
        "apiVersion": API_VERSION,
        "kind": "Harness",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "kagent": {},
            "workload": {"image": image},
            "env": [{"name": "KAGENT_PROPAGATE_TOKEN", "value": "true"}],
            "substrate": {"workerPoolRef": {"name": worker_pool}, "snapshotPolicy": {"location": SNAPSHOT_LOCATION}},
            "allowedAgentTemplates": {"selector": {"matchLabels": {HARNESS_LABEL: name}}},
        },
    }


def ensure_runtime(kube: Kube, helm: Helm) -> None:
    assert_pins_match_ats_config()
    preflight(kube)
    bootstrap_substrate(kube)
    install_substrate(kube, helm)
    install_kagent(kube, helm)
    wait_worker_pool(kube)
    kube.apply(harness_object(HARNESS))
    assert kube.get("modelconfigs.kagent.dev", MODEL_CONFIG, namespace=KAGENT_NAMESPACE), f"the kagent chart rendered no ModelConfig {MODEL_CONFIG}"
    logger.info("runtime up: substrate %s in %s, kagent %s in %s, Harness %s on %s (%s)",
                SUBSTRATE_LINE, SUBSTRATE_NAMESPACE, KAGENT_LINE, KAGENT_NAMESPACE, HARNESS, WORKER_POOL, HARNESS_IMAGE)


def dump_substrate(kube: Kube) -> None:
    kube.dump([f"-n {SUBSTRATE_NAMESPACE} get pods -o wide", f"-n {PODCERT_NAMESPACE} get pods -o wide",
               f"-n {SUBSTRATE_NAMESPACE} get events --sort-by=.lastTimestamp", f"-n {SUBSTRATE_NAMESPACE} logs deployment/ate-controller --tail=80",
               f"-n {SUBSTRATE_NAMESPACE} logs daemonset/atelet --tail=80"])


def dump_kagent(kube: Kube) -> None:
    servers = ("get remotemcpservers.kagent.dev -o custom-columns=NAME:.metadata.name,GENERATION:.metadata.generation,"
               "OBSERVED:.status.observedGeneration,CONDITIONS:.status.conditions[*].type,STATUS:.status.conditions[*].status,REASON:.status.conditions[*].reason")
    kube.dump([f"-n {KAGENT_NAMESPACE} get pods -o wide", f"-n {KAGENT_NAMESPACE} get workerpools.ate.dev -o yaml",
               f"-n {KAGENT_NAMESPACE} get harnesses.kagent.dev -o yaml", f"-n {KAGENT_NAMESPACE} get agenttemplates.kagent.dev -o yaml",
               f"-n {KAGENT_NAMESPACE} {servers}", f"-n {KAGENT_NAMESPACE} get events --sort-by=.lastTimestamp",
               f"-n {KAGENT_NAMESPACE} logs deployment/kagent-controller --tail=300",
               f"-n {KAGENT_NAMESPACE} logs deployment/kagent-controller --previous --tail=40"])


# ---------------------------------------------------------------------------
# Readiness of an AgentTemplate on a Harness
# ---------------------------------------------------------------------------


def harness_status(template: Dict[str, Any], harness: str) -> Optional[Dict[str, Any]]:
    """The Harness's entry in status.harnesses[], None while the controller has not reported on it."""
    for entry in (template.get("status") or {}).get("harnesses") or []:
        if entry.get("harness") == harness:
            return entry
    return None


def condition(entry: Optional[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    for c in (entry or {}).get("conditions") or []:
        if c.get("type") == kind:
            return c
    return {}


def describe(c: Dict[str, Any]) -> str:
    return f"{c.get('type')}={c.get('status')} {c.get('reason')}: {c.get('message')}"


def terminal_failure(entry: Dict[str, Any]) -> Optional[str]:
    """A False condition the controller will not retry: ResolvedRefs or
    Compatible, or Ready for a reason other than the golden boot still
    running. ActorTemplateFailed carries Substrate's own message (an image
    that cannot be pulled, a skill that cannot be materialised)."""
    for c in entry.get("conditions") or []:
        if c.get("status") != "False":
            continue
        if c.get("type") in ("ResolvedRefs", "Compatible") or (c.get("type") == "Ready" and c.get("reason") != READY_PENDING_REASON):
            return describe(c)
    return None


def wait_template_ready(kube: Kube, name: str, harness: str = HARNESS, timeout: float = BOOT_TIMEOUT_S, namespace: str = KAGENT_NAMESPACE) -> Dict[str, Any]:
    """The AgentTemplate's status.harnesses[] entry for the Harness once Ready
    is True for the current generation (and the successful revision is the
    desired one). Fails fast, with the reason, when no Harness admits the
    template, when a condition fails for good, or when the Harness's WorkerPool
    has no ready worker; times out only on a golden boot that is still pending."""
    started = time.monotonic()
    zero_ready_since: List[float] = []

    def poll() -> Any:
        template = kube.get("agenttemplates.kagent.dev", name, namespace=namespace)
        if not template:
            raise FailFast(f"AgentTemplate {namespace}/{name} does not exist")
        generation = template["metadata"]["generation"]
        status = template.get("status") or {}
        entry = harness_status(template, harness)
        if entry is None:
            if status.get("observedGeneration", 0) >= generation:
                harnesses = kube.items("harnesses.kagent.dev", namespace=namespace)
                selectors = ", ".join(
                    f"{h['metadata']['name']} admits {h['spec'].get('allowedAgentTemplates', {}).get('selector', {}).get('matchLabels', {})}" for h in harnesses
                ) or "none in the namespace"
                raise FailFast(
                    f"no Harness admits AgentTemplate {namespace}/{name} (labels {template['metadata'].get('labels', {})};"
                    f" the controller caught up with generation {generation} and reports no Harness). Harnesses: {selectors}"
                )
            return None
        failure = terminal_failure(entry)
        if failure:
            raise FailFast(f"AgentTemplate {namespace}/{name} on Harness {harness} failed for good after {time.monotonic() - started:.0f}s: {failure}")
        ready = condition(entry, "Ready")
        if ready.get("status") == "True" and int(ready.get("observedGeneration") or 0) >= generation and entry.get("latestSuccessfulRevision") == entry.get("desiredRevision"):
            return entry
        # The boot is pending: a pool without a ready worker never boots it.
        harness_obj = kube.get("harnesses.kagent.dev", harness, namespace=namespace) or {}
        pool = harness_obj.get("spec", {}).get("substrate", {}).get("workerPoolRef", {}).get("name")
        if pool:
            if worker_pool_ready(kube, pool, namespace) == 0:
                zero_ready_since.append(time.monotonic())
                if time.monotonic() - zero_ready_since[0] >= NO_READY_WORKER_GRACE_S:
                    raise FailFast(f"AgentTemplate {namespace}/{name} cannot boot: {no_ready_worker_reason(kube, pool, namespace)}")
            else:
                zero_ready_since.clear()
        logger.info("%s on %s: %s", name, harness, describe(ready) if ready else "no Ready condition yet")
        return None

    entry = wait_for(f"AgentTemplate {name} Ready on Harness {harness}", poll, timeout)
    TIMINGS.record(f"AgentTemplate {name} Ready on {harness}", time.monotonic() - started)
    return entry


def assert_all_conditions_true(entry: Dict[str, Any], generation: int) -> None:
    for kind in ("Accepted", "ResolvedRefs", "Compatible", "Ready"):
        c = condition(entry, kind)
        assert c.get("status") == "True", f"{kind} is not True: {describe(c) if c else 'absent'}"
        assert int(c.get("observedGeneration") or 0) >= generation, f"{kind} lags behind generation {generation}: {describe(c)}"


# ---------------------------------------------------------------------------
# Releases of the chart under test
# ---------------------------------------------------------------------------


def install_release(helm: Helm, chart_archive: Path, release: str, values: Optional[Path] = None, sets: Optional[List[str]] = None) -> None:
    """`helm install` of a release of the chart under test into the Harness's
    namespace. No --wait: the chart renders custom resources only, and the
    readiness that matters is asserted by wait_template_ready."""
    helm.install(release, str(chart_archive), KAGENT_NAMESPACE, values=[values] if values else None, sets=sets, wait=False, timeout="2m")


def template_generation(kube: Kube, name: str) -> int:
    template = kube.get("agenttemplates.kagent.dev", name, namespace=KAGENT_NAMESPACE)
    assert template, f"AgentTemplate {KAGENT_NAMESPACE}/{name} does not exist"
    return int(template["metadata"]["generation"])


def remote_mcp_server(kube: Kube, name: str) -> Optional[Dict[str, Any]]:
    return kube.get("remotemcpservers.kagent.dev", name, namespace=KAGENT_NAMESPACE)


def wait_server_accepted(kube: Kube, name: str, timeout: float = SERVER_TIMEOUT_S) -> Dict[str, Any]:
    """The agent's RemoteMCPServer once the controller has reported on it:
    Accepted True and no failed condition. With the discovery opt-out the
    controller accepts the server without connecting to it (agents resolve the
    tool list at run time), so a failed condition is a failure, not a retry.
    The discovery reconciler runs on its own queue, so the status may land
    after the template's — hence a wait, not a read."""

    seen: List[str] = []

    def poll() -> Any:
        server = remote_mcp_server(kube, name)
        if not server:
            raise FailFast(f"RemoteMCPServer {KAGENT_NAMESPACE}/{name} does not exist")
        status = server.get("status") or {}
        failed = [describe(c) for c in status.get("conditions") or [] if c.get("status") == "False"]
        if failed:
            raise FailFast(f"RemoteMCPServer {KAGENT_NAMESPACE}/{name} has failed conditions: {failed}")
        seen[:] = [f"generation {server['metadata']['generation']}, status {json.dumps(status)[:300]}"]
        return server if condition(status, "Accepted").get("status") == "True" else None

    try:
        return wait_for(f"RemoteMCPServer {name} Accepted", poll, timeout)
    except AssertionError as exc:
        if isinstance(exc, FailFast):
            raise
        raise AssertionError(f"{exc}; the server's last state: {seen[0] if seen else 'never read'}") from exc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def log_heartbeat() -> Iterator[None]:
    """One log line a minute so CircleCI's no-output timeout never fires during
    a silent `helm install --wait`."""
    stop = threading.Event()

    def beat() -> None:
        minutes = 0
        while not stop.wait(60):
            minutes += 1
            logger.info("heartbeat: %d min elapsed, still waiting/working", minutes)

    threading.Thread(target=beat, name="log-heartbeat", daemon=True).start()
    yield
    stop.set()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Iterator[None]:
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())


@pytest.fixture(autouse=True)
def dump_on_failure(request: pytest.FixtureRequest) -> Iterator[None]:
    """The runtime's state in the log when a test fails, so a red CI run explains itself."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed and "kube" in request.node.funcargs:
        dump_kagent(request.node.funcargs["kube"])


@pytest.fixture(scope="module")
def kube(kube_cluster: Cluster) -> Kube:
    return Kube(kube_cluster.kube_config_path)


@pytest.fixture(scope="module")
def helm(kube_cluster: Cluster) -> Helm:
    return Helm(kube_cluster.kube_config_path)


@pytest.fixture(scope="module")
def chart_archive(chart_path: str) -> Path:
    """The archive under test. ATS names it in ATS_CHART_PATH relative to its
    working directory (the repository root, where the CI job copies the
    archive), while pytest runs in tests/ats — so a relative name is resolved
    against the root, or `helm install` reads it as a repository reference."""
    archive = Path(chart_path)
    if not archive.is_absolute():
        archive = REPO_ROOT / archive
    assert archive.is_file(), f"chart archive not found: {archive}"
    return archive


@pytest.fixture(scope="module")
def runtime(kube: Kube, helm: Helm) -> None:
    """Substrate, kagent and the platform Harness up before any release of the
    chart; a no-op on a cluster that already runs them (the functional scenario)."""
    started = time.monotonic()
    ensure_runtime(kube, helm)
    TIMINGS.record("runtime (bootstrap, substrate, kagent, WorkerPool, Harness)", time.monotonic() - started)


@pytest.fixture
def release(kube: Kube, helm: Helm, chart_archive: Path, runtime: None) -> Iterator[Callable[..., None]]:
    """Installs releases of the chart under test and uninstalls them afterwards."""
    installed: List[str] = []

    def install(name: str, values: Optional[Path] = None, sets: Optional[List[str]] = None) -> None:
        install_release(helm, chart_archive, name, values, sets)
        installed.append(name)

    yield install
    for name in reversed(installed):
        helm.uninstall(name, KAGENT_NAMESPACE)
