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


def trigger_job(name_prefix: str = "data-processing-manual") -> str:
    """Cria um Job a partir do CronJob data-processing e retorna o nome do Job."""
    job_name = f"{name_prefix}-{int(time.time())}"
    pc.run(
        [
            "kubectl", "create", "job",
            "--from=cronjob/data-processing", job_name,
            "-n", NAMESPACE,
        ]
    )
    return job_name


def main() -> None:
    trigger_job()


if __name__ == "__main__":
    main()
