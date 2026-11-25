"""deploy/helm/rad-shift: what the chart renders (roadmap item 30).

Renders with the real `helm template` and checks the rendered objects, so
the tests read like the cluster would. Marked `helm`: CI runs them in the
kubernetes job, which installs helm (and validates the output against the
Kubernetes schemas with kubeconform).
"""

import shutil
import subprocess  # nosec B404 - runs helm with fixed arguments, never a shell
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "rad-shift"
KIND_CONFIG = ROOT / "deploy" / "kind" / "cluster.yaml"
TRAEFIK_VALUES = ROOT / "deploy" / "kind" / "traefik-values.yaml"
APPLICATION = ROOT / "deploy" / "argocd" / "application.yaml"
KIND_SCRIPT = ROOT / "scripts" / "kind_cluster.sh"
RELEASE = "rad-shift"

pytestmark = pytest.mark.helm


def render(*settings: str) -> list[dict]:
    if shutil.which("helm") is None:
        pytest.skip("needs helm")
    args = [arg for setting in settings for arg in ("--set", setting)]
    output = subprocess.run(  # nosec B603 B607 - fixed helm command
        ["helm", "template", RELEASE, str(CHART), *args],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout  # fmt: skip
    return [doc for doc in yaml.safe_load_all(output) if doc]


def render_error(*settings: str) -> str:
    try:
        render(*settings)
    except subprocess.CalledProcessError as error:
        return error.stderr
    raise AssertionError("helm template succeeded")


def find(docs: list[dict], kind: str, component: str) -> dict:
    matches = [
        doc for doc in docs
        if doc["kind"] == kind
        and doc["metadata"]["labels"]["app.kubernetes.io/component"] == component
    ]  # fmt: skip
    assert len(matches) == 1, f"one {kind} for {component}, found {len(matches)}"
    return matches[0]


def kinds(docs: list[dict]) -> set[tuple[str, str]]:
    return {(doc["kind"], doc["metadata"]["labels"]["app.kubernetes.io/component"]) for doc in docs}


def workloads(docs: list[dict]) -> list[dict]:
    return [doc for doc in docs if doc["kind"] in ("Deployment", "StatefulSet")]


def pod(workload: dict) -> dict:
    return workload["spec"]["template"]["spec"]


def container(workload: dict) -> dict:
    (only,) = pod(workload)["containers"]
    return only


def env(workload: dict) -> dict[str, str]:
    return {item["name"]: item.get("value") for item in container(workload).get("env", [])}


@pytest.fixture(scope="module")
def default() -> list[dict]:
    return render()


class TestWhatItDeploys:
    def test_the_whole_app_by_default(self, default):
        assert kinds(default) == {
            ("ConfigMap", "config"),
            ("Deployment", "backend"), ("Service", "backend"),
            ("PodDisruptionBudget", "backend"), ("HorizontalPodAutoscaler", "backend"),
            ("Deployment", "worker"),
            ("Deployment", "aggregator"),
            ("Deployment", "frontend"), ("Service", "frontend"),
            ("StatefulSet", "postgres"), ("Service", "postgres"),
            ("StatefulSet", "kafka"), ("Service", "kafka"),
            ("Ingress", "ingress"),
        }  # fmt: skip

    def test_no_secret_is_rendered(self, default):
        """Secrets live outside Git; the chart only refers to one by name."""
        assert not [doc for doc in default if doc["kind"] == "Secret"]
        backend = find(default, "Deployment", "backend")
        refs = [ref for ref in container(backend)["envFrom"] if "secretRef" in ref]
        assert refs == [{"secretRef": {"name": "rad-shift"}}]

    def test_an_image_tag_is_required(self):
        assert "an image tag is required" in render_error("backend.image.tag=")


class TestHardening:
    def test_every_pod_runs_as_a_non_root_user(self, default):
        for workload in workloads(default):
            security = pod(workload)["securityContext"]
            assert security["runAsNonRoot"] is True, workload["metadata"]["name"]
            assert security["runAsUser"] != 0
            assert security["seccompProfile"] == {"type": "RuntimeDefault"}

    def test_every_container_is_locked_down(self, default):
        for workload in workloads(default):
            spec = pod(workload)
            for each in [*spec["containers"], *spec.get("initContainers", [])]:
                security = each["securityContext"]
                assert security["allowPrivilegeEscalation"] is False, each["name"]
                assert security["readOnlyRootFilesystem"] is True, each["name"]
                assert security["capabilities"] == {"drop": ["ALL"]}, each["name"]

    def test_deployments_keep_a_few_revisions_to_roll_back_to(self, default):
        for deployment in (doc for doc in default if doc["kind"] == "Deployment"):
            assert deployment["spec"]["revisionHistoryLimit"] == 3, deployment["metadata"]["name"]

    def test_every_container_has_requests_and_a_memory_limit(self, default):
        for workload in workloads(default):
            spec = pod(workload)
            for each in [*spec["containers"], *spec.get("initContainers", [])]:
                assert {"cpu", "memory"} <= set(each["resources"]["requests"]), each["name"]
                assert "memory" in each["resources"]["limits"], each["name"]


class TestTheApi:
    def test_the_hpa_owns_the_replica_count(self, default):
        """A replicas field would reset the HPA's count on every upgrade or sync."""
        backend = find(default, "Deployment", "backend")
        hpa = find(default, "HorizontalPodAutoscaler", "backend")
        assert "replicas" not in backend["spec"]
        assert hpa["spec"]["scaleTargetRef"]["name"] == backend["metadata"]["name"]
        assert hpa["spec"]["minReplicas"] >= 2, "one pod down still leaves one serving"

    def test_without_autoscaling_the_count_is_fixed(self):
        docs = render("backend.autoscaling.enabled=false", "backend.replicas=3")
        assert ("HorizontalPodAutoscaler", "backend") not in kinds(docs)
        assert find(docs, "Deployment", "backend")["spec"]["replicas"] == 3

    def test_liveness_does_not_depend_on_the_database(self, default):
        """A database outage takes pods out of service; restarting them all fixes nothing."""
        api = container(find(default, "Deployment", "backend"))
        assert api["readinessProbe"]["httpGet"]["path"] == "/health"
        assert api["livenessProbe"]["httpGet"]["path"] == "/health/live"
        assert api["startupProbe"]["httpGet"]["path"] == "/health/live"

    def test_rollouts_never_drop_below_the_current_count(self, default):
        strategy = find(default, "Deployment", "backend")["spec"]["strategy"]
        assert strategy["rollingUpdate"]["maxUnavailable"] == 0

    def test_a_settings_change_restarts_the_pods(self, default):
        def checksum(docs):
            annotations = find(docs, "Deployment", "backend")["spec"]["template"]["metadata"]
            return annotations["annotations"]["checksum/config"]

        changed = render("backend.env.LOG_LEVEL=debug")
        assert checksum(changed) != checksum(default)
        assert find(changed, "ConfigMap", "config")["data"]["LOG_LEVEL"] == "debug"


class TestOneScheduler:
    def test_the_api_leaves_scheduling_to_one_worker_pod(self, default):
        worker = find(default, "Deployment", "worker")
        assert env(find(default, "Deployment", "backend"))["GENERATOR_SCHEDULER_ENABLED"] == "false"
        assert worker["spec"]["replicas"] == 1
        assert worker["spec"]["strategy"] == {"type": "Recreate"}, "never two during a rollout"
        assert container(worker)["command"] == ["python", "-m", "app.generators.worker"]

    def test_without_the_worker_the_api_schedules(self):
        docs = render("worker.enabled=false")
        assert ("Deployment", "worker") not in kinds(docs)
        assert "GENERATOR_SCHEDULER_ENABLED" not in env(find(docs, "Deployment", "backend"))


class TestDependencies:
    def test_without_kafka_nothing_publishes_and_nothing_aggregates(self):
        docs = render("kafka.enabled=false")
        assert ("StatefulSet", "kafka") not in kinds(docs)
        assert ("Deployment", "aggregator") not in kinds(docs)
        assert "KAFKA_BOOTSTRAP_SERVERS" not in find(docs, "ConfigMap", "config")["data"]

    def test_the_app_finds_kafka_by_its_service(self, default):
        config = find(default, "ConfigMap", "config")["data"]
        kafka = find(default, "Service", "kafka")
        assert config["KAFKA_BOOTSTRAP_SERVERS"] == f"{kafka['metadata']['name']}:9092"

    def test_kafka_gets_no_service_link_variables(self, default):
        """The image reads every KAFKA_* variable as config, KAFKA_PORT=tcp://... included."""
        assert pod(find(default, "StatefulSet", "kafka"))["enableServiceLinks"] is False

    def test_kafka_can_write_its_logs(self, default):
        """A read-only root filesystem: without a volume here the JVM won't start (GC log)."""
        kafka = container(find(default, "StatefulSet", "kafka"))
        assert "/opt/kafka/logs" in {mount["mountPath"] for mount in kafka["volumeMounts"]}

    def test_waiting_for_postgres_names_a_database_user(self, default):
        """Without -U, pg_isready looks up the OS user; uid 1000 has none there: "no attempt"."""
        init = pod(find(default, "Deployment", "backend"))["initContainers"][0]
        assert '-U "$DB_USER"' in init["command"][-1]
        assert {"name": "DB_USER", "value": "radshift"} in init["env"]

    def test_an_external_database_replaces_the_in_cluster_one(self):
        docs = render("postgres.enabled=false", "postgres.host=db.example.internal")
        assert ("StatefulSet", "postgres") not in kinds(docs)
        assert find(docs, "ConfigMap", "config")["data"]["DB_HOST"] == "db.example.internal"
        init = pod(find(docs, "Deployment", "backend"))["initContainers"][0]
        assert {"name": "DB_HOST", "value": "db.example.internal"} in init["env"]

    def test_an_external_database_needs_a_host(self):
        assert "postgres.host is required" in render_error("postgres.enabled=false")

    def test_the_database_volume_outlives_the_release(self, default):
        postgres = find(default, "StatefulSet", "postgres")
        assert postgres["spec"]["persistentVolumeClaimRetentionPolicy"]["whenDeleted"] == "Retain"


class TestWiring:
    def test_every_service_selects_a_workloads_pods(self, default):
        pod_labels = [w["spec"]["template"]["metadata"]["labels"] for w in workloads(default)]
        for service in (doc for doc in default if doc["kind"] == "Service"):
            selector = service["spec"]["selector"]
            assert any(selector.items() <= labels.items() for labels in pod_labels), service[
                "metadata"
            ]["name"]

    def test_every_service_port_is_a_named_container_port(self, default):
        for service in (doc for doc in default if doc["kind"] == "Service"):
            component = service["metadata"]["labels"]["app.kubernetes.io/component"]
            workload = next(w for w in workloads(default)
                            if w["metadata"]["labels"]["app.kubernetes.io/component"] == component)  # fmt: skip
            names = {port["name"] for port in container(workload)["ports"]}
            for port in service["spec"]["ports"]:
                assert port["targetPort"] in names, service["metadata"]["name"]

    def test_the_ingress_routes_each_host_to_a_service(self, default):
        ingress = find(default, "Ingress", "ingress")
        services = {doc["metadata"]["name"]: doc for doc in default if doc["kind"] == "Service"}
        routes = {
            rule["host"]: rule["http"]["paths"][0]["backend"]["service"]
            for rule in ingress["spec"]["rules"]
        }
        assert routes["rad-shift.localhost"]["name"] == "rad-shift-frontend"
        assert routes["api.rad-shift.localhost"]["name"] == "rad-shift-backend"
        for route in routes.values():
            ports = {port["name"] for port in services[route["name"]]["spec"]["ports"]}
            assert route["port"]["name"] in ports

    def test_the_frontend_calls_the_api_service_from_inside(self, default):
        frontend = find(default, "Deployment", "frontend")
        assert env(frontend)["API_INTERNAL_URL"] == "http://rad-shift-backend:5000"


class TestLocalCluster:
    """deploy/kind/, the script and the chart's defaults agree on ports and hosts."""

    def test_the_published_port_reaches_the_ingress_controller(self):
        (node,) = yaml.safe_load(KIND_CONFIG.read_text())["nodes"]
        (mapping,) = node["extraPortMappings"]
        traefik = yaml.safe_load(TRAEFIK_VALUES.read_text())
        values = yaml.safe_load((CHART / "values.yaml").read_text())

        assert mapping["containerPort"] == traefik["ports"]["web"]["nodePort"]
        assert mapping["listenAddress"] == "127.0.0.1", "loopback only"
        assert (
            values["publicUrl"]
            == f"http://{values['ingress']['frontendHost']}:{mapping['hostPort']}"
        )
        assert (
            f"API_URL=http://{values['ingress']['apiHost']}:{mapping['hostPort']}"
            in KIND_SCRIPT.read_text()
        )

    def test_the_node_image_is_pinned_by_digest(self):
        (node,) = yaml.safe_load(KIND_CONFIG.read_text())["nodes"]
        assert "@sha256:" in node["image"]


class TestGitOps:
    def test_argo_cd_tracks_this_chart(self):
        """The public mirror: Argo CD needs no Git credential to read it."""
        source = yaml.safe_load(APPLICATION.read_text())["spec"]["source"]
        assert source["repoURL"].endswith("/rad-shift-showcase.git")
        assert (ROOT / source["path"]) == CHART

    def test_argo_cd_prunes_and_self_heals(self):
        automated = yaml.safe_load(APPLICATION.read_text())["spec"]["syncPolicy"]["automated"]
        assert automated == {"prune": True, "selfHeal": True}
