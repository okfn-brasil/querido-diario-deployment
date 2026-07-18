#!/usr/bin/env python3
"""k8s_local_data_processing.py — Dispara manualmente o CronJob data-processing
no cluster local (equivalente a `kubectl create job --from=cronjob/... nome-$(date +%s)`,
sem depender de `date` de shell POSIX)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

NAMESPACE = "querido-diario"


def main() -> None:
    job_name = f"data-processing-manual-{int(time.time())}"
    pc.run(
        [
            "kubectl", "create", "job",
            "--from=cronjob/data-processing", job_name,
            "-n", NAMESPACE,
        ]
    )


if __name__ == "__main__":
    main()
