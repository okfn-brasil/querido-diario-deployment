import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
