import io
import json
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import k8s_local_monitoring as km  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
VALUES = ROOT / "k8s" / "local" / "monitoring" / "values-local.yaml"
DASHBOARDS = ROOT / "k8s" / "local" / "monitoring" / "dashboards"
CTX = "kind-querido-diario-dev"


class ValuesLocalTest(unittest.TestCase):
    """Os testes do repo são só stdlib (sem PyYAML): checagens por texto/regex."""

    @classmethod
    def setUpClass(cls):
        cls.text = VALUES.read_text(encoding="utf-8")
        cls.code = "\n".join(l for l in cls.text.splitlines() if not l.lstrip().startswith("#"))

    def test_cluster_name_local(self):
        self.assertRegex(self.code, r"(?m)^cluster:\n  name: local$")

    def test_pod_logs_restricted_to_app_namespace(self):
        self.assertRegex(
            self.code,
            r"(?m)^podLogsViaLoki:\n  enabled: true\n(?:  .*\n)*?  namespaces:\n    - querido-diario$",
        )

    def test_node_exporter_deployed(self):
        self.assertRegex(self.code, r"(?m)^  node-exporter:\n    deploy: true$")

    def test_destinations_point_to_monitoring_namespace(self):
        self.assertRegex(
            self.code,
            r"(?m)^  prometheus:\n    type: prometheus\n    url: http://[\w.-]+\.monitoring\.svc[\w.]*/\S*$",
        )
        self.assertRegex(
            self.code,
            r"(?m)^  loki:\n    type: loki\n    url: http://[\w.-]+\.monitoring\.svc[\w.]*:3100/\S*$",
        )

    def test_no_fleet_management(self):
        self.assertNotIn("remoteConfig", self.code)

    @unittest.skipUnless(shutil.which("helm"), "helm não instalado")
    def test_values_render_with_chart(self):
        listed = subprocess.run(
            ["helm", "search", "repo", "grafana/k8s-monitoring", "--version", km.K8S_MONITORING_VERSION],
            capture_output=True, text=True,
        )
        if "grafana/k8s-monitoring" not in listed.stdout:
            self.skipTest("repositório helm 'grafana' não configurado")
        res = subprocess.run(
            ["helm", "template", "t", "grafana/k8s-monitoring", "--version", km.K8S_MONITORING_VERSION,
             "-n", "monitoring", "-f", str(VALUES)],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('names = ["querido-diario"]', res.stdout)


class DashboardsTest(unittest.TestCase):
    def test_dashboards_are_valid_json(self):
        files = sorted(DASHBOARDS.glob("*.json"))
        titles = set()
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            titles.add(d["title"])
        self.assertLessEqual({"Kubernetes / Pods", "Logs do querido-diario"}, titles)

    def test_configmap_has_sidecar_label(self):
        f = DASHBOARDS / "querido-diario-logs.json"
        cm = km.dashboard_configmap(f)
        self.assertIn("kind: ConfigMap", cm)
        self.assertIn("namespace: monitoring", cm)
        self.assertIn('grafana_dashboard: "1"', cm)
        self.assertIn("querido-diario-logs.json:", cm)


class Recorder:
    """Substitui subprocess.run: registra comandos e simula `get-contexts`."""

    def __init__(self, contexts=CTX + "\n"):
        self.calls = []
        self.contexts = contexts

    def __call__(self, cmd, *a, **kw):
        cmd = list(cmd)
        self.calls.append(cmd)
        out = self.contexts if cmd[:3] == ["kubectl", "config", "get-contexts"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


def cluster_calls(rec):
    return [c for c in rec.calls if c[0] in ("kubectl", "helm") and c[:3] != ["kubectl", "config", "get-contexts"]]


class PinnedContextTest(unittest.TestCase):
    def run_cmd(self, cmd, rec):
        with mock.patch.object(km.subprocess, "run", rec), \
                mock.patch.object(km.pc, "check_docker"), \
                mock.patch.object(km.pc, "ensure_helm"), \
                mock.patch.object(km.pc, "ensure_kubectl"), \
                mock.patch.object(km, "warn_if_low_memory"), \
                mock.patch.object(km.pc, "port_in_use", return_value=False), \
                redirect_stdout(io.StringIO()):
            return km.main(["k8s_local_monitoring.py", cmd])

    def test_every_command_is_pinned(self):
        for cmd in ("up", "down", "status", "grafana"):
            with self.subTest(cmd=cmd):
                rec = Recorder()
                self.run_cmd(cmd, rec)
                calls = cluster_calls(rec)
                self.assertTrue(calls, "nenhum comando kubectl/helm executado")
                for c in calls:
                    if c[0] == "kubectl":
                        self.assertEqual(c[1:3], ["--context", CTX], c)
                    else:
                        self.assertEqual(c[1:3], ["--kube-context", CTX], c)

    def test_up_installs_four_releases_in_monitoring(self):
        rec = Recorder()
        self.run_cmd("up", rec)
        installs = [c for c in rec.calls if "upgrade" in c and "--install" in c]
        self.assertEqual(
            [c[c.index("--install") + 1] for c in installs],
            ["prometheus", "loki", "grafana", "k8s-monitoring"],
        )
        for c in installs:
            self.assertIn("monitoring", c)
            self.assertIn("--version", c)

    def test_missing_context_aborts_before_any_action(self):
        for cmd in ("up", "down", "status", "grafana"):
            with self.subTest(cmd=cmd):
                rec = Recorder(contexts="openknowledge\n")
                err = io.StringIO()
                with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                    self.run_cmd(cmd, rec)
                self.assertNotEqual(cm.exception.code, 0)
                self.assertIn(CTX, err.getvalue())
                self.assertEqual(cluster_calls(rec), [])

    def test_never_uses_current_context(self):
        for cmd in ("up", "down", "status", "grafana"):
            rec = Recorder()
            self.run_cmd(cmd, rec)
            for c in rec.calls:
                self.assertNotIn("use-context", c)


class MemoryWarningTest(unittest.TestCase):
    def test_warns_when_low(self):
        with mock.patch.object(km, "available_memory_gib", return_value=2.0), \
                mock.patch.object(km.pc, "warn") as w:
            km.warn_if_low_memory()
        w.assert_called_once()

    def test_silent_when_enough_or_unknown(self):
        for v in (8.0, None):
            with mock.patch.object(km, "available_memory_gib", return_value=v), \
                    mock.patch.object(km.pc, "warn") as w:
                km.warn_if_low_memory()
            w.assert_not_called()


if __name__ == "__main__":
    unittest.main()
