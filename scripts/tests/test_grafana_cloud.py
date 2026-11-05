import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import grafana_cloud as gc  # noqa: E402


def doc(kind: str, name: str) -> str:
    return f"apiVersion: v1\nkind: {kind}\nmetadata:\n  name: {name}\n"


class ClusterScopedTest(unittest.TestCase):
    def test_detects_clusterrole(self):
        self.assertEqual(gc.cluster_scoped_resources(doc("ClusterRole", "x")), ["ClusterRole/x"])

    def test_ignores_namespaced(self):
        y = doc("Deployment", "a") + "---\n" + doc("Role", "b")
        self.assertEqual(gc.cluster_scoped_resources(y), [])

    def test_detects_crd_and_webhooks(self):
        kinds = [
            "CustomResourceDefinition",
            "MutatingWebhookConfiguration",
            "ValidatingWebhookConfiguration",
            "ClusterRoleBinding",
        ]
        y = "---\n".join(doc(k, "n") for k in kinds)
        self.assertEqual(gc.cluster_scoped_resources(y), [f"{k}/n" for k in kinds])

    def test_multi_document_and_empty_docs(self):
        y = "---\n---\n" + doc("ClusterRole", "a") + "---\n\n---\n# só comentário\n---\n" + doc("Namespace", "z")
        self.assertEqual(gc.cluster_scoped_resources(y), ["ClusterRole/a", "Namespace/z"])

    def test_name_is_metadata_name_not_nested_label(self):
        y = (
            "apiVersion: v1\nkind: ClusterRole\nmetadata:\n  labels:\n"
            "    name: wrong\n  name: right\n"
        )
        self.assertEqual(gc.cluster_scoped_resources(y), ["ClusterRole/right"])


class TemplateArgsTest(unittest.TestCase):
    def test_template_args(self):
        args = gc._template_args("4.5.3", Path("v.yaml"))
        self.assertEqual(args[0:2], ["helm", "template"])
        self.assertIn("4.5.3", args)
        self.assertIn("--include-crds", args)

    def test_no_helm_upgrade_path(self):
        self.assertFalse(hasattr(gc, "helm_args"))
        self.assertFalse(hasattr(gc, "rollback"))


class ChartVersionTest(unittest.TestCase):
    def test_env_value(self):
        self.assertEqual(gc.chart_version_from_env({"GRAFANA_CLOUD_CHART_VERSION": "9.9.9"}), "9.9.9")

    def test_unset_and_empty_fall_back(self):
        self.assertEqual(gc.chart_version_from_env({}), "4.5.3")
        self.assertEqual(gc.chart_version_from_env({"GRAFANA_CLOUD_CHART_VERSION": ""}), "4.5.3")


KUBECTL_APPLY = ["kubectl", "apply", "-n", "querido-diario", "-f", "-"]


class FriendlyErrorTest(unittest.TestCase):
    def test_status_missing_kubectl_is_friendly(self):
        err = io.StringIO()
        with mock.patch.object(gc.subprocess, "run", side_effect=FileNotFoundError("kubectl")), \
                redirect_stderr(err):
            rc = gc.main(["grafana_cloud.py", "status"])
        self.assertEqual(rc, 1)
        self.assertIn("comando não encontrado: kubectl", err.getvalue())

    def test_install_missing_kubectl_is_friendly(self):
        err = io.StringIO()
        with mock.patch.object(gc, "check", return_value=0), \
                mock.patch.object(gc, "credentials_secret_exists", return_value=True), \
                mock.patch.object(gc, "render", return_value="m"), \
                mock.patch.object(gc.subprocess, "run", side_effect=FileNotFoundError("kubectl")), \
                redirect_stderr(err):
            rc = gc.main(["grafana_cloud.py", "install"])
        self.assertEqual(rc, 1)
        self.assertIn("comando não encontrado: kubectl", err.getvalue())

    def test_rollback_is_no_longer_a_command(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = gc.main(["grafana_cloud.py", "rollback"])
        self.assertEqual(rc, 2)
        self.assertNotIn("rollback", err.getvalue())


class StatusTest(unittest.TestCase):
    def test_filters_grafana_cloud_lines_and_keeps_header(self):
        out = (
            "NAME                       READY   STATUS\n"
            "pod/api-1                  1/1     Running\n"
            "pod/grafana-cloud-alloy-x  2/2     Running\n"
            "deployment.apps/redis      1/1     1\n"
            "service/grafana-cloud-otel-receiver   ClusterIP\n"
        )
        cp = mock.Mock(stdout=out)
        buf = io.StringIO()
        with mock.patch.object(gc, "_captured", return_value=cp) as cap, redirect_stdout(buf):
            rc = gc.status()
        self.assertEqual(rc, 0)
        cap.assert_called_once_with(
            ["kubectl", "get", "alloy,daemonset,deployment,service,pod", "-n", "querido-diario"]
        )
        self.assertEqual(
            buf.getvalue().splitlines(),
            [
                "NAME                       READY   STATUS",
                "pod/grafana-cloud-alloy-x  2/2     Running",
                "service/grafana-cloud-otel-receiver   ClusterIP",
            ],
        )


class InstallTest(unittest.TestCase):
    def _patches(self, check=0, secret=True, manifest="MANIFEST"):
        return (
            mock.patch.object(gc, "check", return_value=check),
            mock.patch.object(gc, "credentials_secret_exists", return_value=secret),
            mock.patch.object(gc, "render", return_value=manifest),
        )

    def test_pipes_rendered_manifest_to_kubectl_apply(self):
        p1, p2, p3 = self._patches()
        with p1, p2, p3, mock.patch.object(gc.subprocess, "run",
                                           return_value=mock.Mock(returncode=0)) as run:
            rc = gc.install()
        self.assertEqual(rc, 0)
        run.assert_called_once_with(KUBECTL_APPLY, input="MANIFEST", text=True)

    def test_surfaces_kubectl_exit_code(self):
        p1, p2, p3 = self._patches()
        with p1, p2, p3, mock.patch.object(gc.subprocess, "run",
                                           return_value=mock.Mock(returncode=7)):
            self.assertEqual(gc.install(), 7)

    def test_check_runs_before_secret_and_render(self):
        order = []
        with mock.patch.object(gc, "check", side_effect=lambda: order.append("check") or 0), \
                mock.patch.object(gc, "credentials_secret_exists",
                                  side_effect=lambda: order.append("secret") or True), \
                mock.patch.object(gc, "render", side_effect=lambda *a: order.append("render") or "m"), \
                mock.patch.object(gc.subprocess, "run", return_value=mock.Mock(returncode=0))as run:
            gc.install()
        self.assertEqual(order, ["check", "secret", "render"])
        run.assert_called_once()

    def test_cluster_scoped_check_failure_aborts(self):
        p1, p2, p3 = self._patches(check=1)
        with p1, p2 as secret, p3 as rend, mock.patch.object(gc.subprocess, "run") as run:
            self.assertEqual(gc.install(), 1)
        run.assert_not_called()
        secret.assert_not_called()
        rend.assert_not_called()

    def test_missing_secret_aborts_before_kubectl_apply(self):
        err = io.StringIO()
        with mock.patch.object(gc, "check", return_value=0), \
                mock.patch.object(gc, "credentials_secret_exists", return_value=False), \
                mock.patch.object(gc, "render") as rend, \
                mock.patch.object(gc.subprocess, "run") as run, \
                redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            gc.main(["grafana_cloud.py", "install"])
        self.assertEqual(cm.exception.code, 1)
        run.assert_not_called()
        rend.assert_not_called()
        self.assertIn("kubectl create secret generic grafana-cloud-credentials", err.getvalue())

    def test_credentials_secret_exists_uses_run_ok(self):
        with mock.patch.object(gc.pc, "run_ok", return_value=True) as ok:
            self.assertTrue(gc.credentials_secret_exists())
        ok.assert_called_once_with(
            ["kubectl", "get", "secret", "grafana-cloud-credentials", "-n", "querido-diario"]
        )


if __name__ == "__main__":
    unittest.main()
