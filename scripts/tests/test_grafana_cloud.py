import io
import sys
import unittest
from contextlib import redirect_stderr
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


class HelmArgsTest(unittest.TestCase):
    def test_install(self):
        self.assertEqual(
            gc.helm_args("install", "4.5.3", Path("v.yaml")),
            ["helm", "upgrade", "--install", "grafana-cloud", "grafana/k8s-monitoring",
             "--version", "4.5.3", "-n", "querido-diario", "-f", "v.yaml",
             "--atomic", "--timeout", "10m"],
        )

    def test_diff_is_helm_template(self):
        args = gc.helm_args("diff", "4.5.3", Path("v.yaml"))
        self.assertEqual(args[0:2], ["helm", "template"])
        self.assertIn("4.5.3", args)

    def test_unknown_action(self):
        with self.assertRaises(ValueError):
            gc.helm_args("nope", "4.5.3", Path("v.yaml"))


class InstallTest(unittest.TestCase):
    def test_missing_secret_aborts_before_helm(self):
        err = io.StringIO()
        with mock.patch.object(gc, "check", return_value=0), \
                mock.patch.object(gc, "credentials_secret_exists", return_value=False), \
                mock.patch.object(gc.subprocess, "run") as run, \
                redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            gc.main(["grafana_cloud.py", "install"])
        self.assertEqual(cm.exception.code, 1)
        run.assert_not_called()
        self.assertIn("kubectl create secret generic grafana-cloud-credentials", err.getvalue())

    def test_credentials_secret_exists_uses_run_ok(self):
        with mock.patch.object(gc.pc, "run_ok", return_value=True) as ok:
            self.assertTrue(gc.credentials_secret_exists())
        ok.assert_called_once_with(
            ["kubectl", "get", "secret", "grafana-cloud-credentials", "-n", "querido-diario"]
        )


if __name__ == "__main__":
    unittest.main()
