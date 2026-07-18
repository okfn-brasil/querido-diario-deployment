#!/usr/bin/env python3
"""spider.py — setup/list/run dos raspadores (Scrapy) localmente.

Substitui os targets spider-setup/spider-list/run-spider do Makefile, que
dependiam de `.venv/bin/` (inexistente no Windows, onde é `.venv/Scripts/`)
e de `source .local.env` (sintaxe bash).

Uso:
    python3 scripts/spider.py setup  [--qd-dir PATH]
    python3 scripts/spider.py list   [--qd-dir PATH]
    python3 scripts/spider.py run SPIDER [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--qd-dir PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

DEFAULT_QD_DIR = pc.REPO_ROOT.parent / "querido-diario"

# requirements.txt pina versões antigas (ex: lxml==4.9.3) sem wheel pra
# versões recentes do Python (3.13+) — força build a partir do source, que
# exige headers de sistema (libxml2-dev/libxslt-dev). Preferimos criar o
# venv com uma versão de Python mais antiga (via pyenv, se disponível) pra
# evitar isso.
COMPATIBLE_PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]

NAMESPACE = "querido-diario"
POSTGRES_SVC = "postgres-rw"
POSTGRES_FORWARD_PORT = 5434
GAZETTES_DB = "queridodiario"

GARAGE_SVC = "garage"
GARAGE_S3_REMOTE_PORT = 3900
GARAGE_S3_FORWARD_PORT = 3910
GARAGE_REGION = "us-east-1"


def data_collection_dir(qd_dir: Path) -> Path:
    return qd_dir / "data_collection"


def venv_dir(qd_dir: Path) -> Path:
    return data_collection_dir(qd_dir) / ".venv"


def venv_bin(qd_dir: Path) -> Path:
    v = venv_dir(qd_dir)
    return v / ("Scripts" if pc.IS_WINDOWS else "bin")


def venv_python(qd_dir: Path) -> Path:
    return venv_bin(qd_dir) / pc.exe("python")


def venv_scrapy(qd_dir: Path) -> Path:
    return venv_bin(qd_dir) / pc.exe("scrapy")


def setup_venv(qd_dir: Path) -> None:
    dc_dir = data_collection_dir(qd_dir)
    requirements = dc_dir / "requirements.txt"
    if not requirements.exists():
        pc.err(f"requirements.txt não encontrado em {requirements} — confira QD_DIR.")

    python_bin = pc.find_python(COMPATIBLE_PYTHON_VERSIONS)
    pc.info(f"Usando interpretador: {python_bin}")
    pc.log(f"Criando venv em {venv_dir(qd_dir)}...")
    pc.run([python_bin, "-m", "venv", str(venv_dir(qd_dir))])

    pip = venv_bin(qd_dir) / pc.exe("pip")
    pc.run([str(pip), "install", "--upgrade", "pip"])
    # requirements.txt usa --hash (modo --require-hashes do pip), mas não
    # pina setuptools — é dependência transitiva implícita do Scrapy. Numa
    # venv nova, o setuptools do ensurepip às vezes já satisfaz isso sem
    # baixar nada; em outras (varia por patch do Python/pip instalados),
    # o pip tenta buscar uma versão nova, sem hash, e o --require-hashes
    # rejeita com "must have their versions pinned with ==". Pinamos aqui
    # pra tornar o resultado determinístico entre máquinas.
    pc.run([str(pip), "install", "setuptools==79.0.1"])
    pc.run([str(pip), "install", "-r", str(requirements)])
    pc.log("Ambiente dos raspadores pronto.")


def cmd_setup(args: argparse.Namespace) -> None:
    setup_venv(args.qd_dir)


def _require_venv(qd_dir: Path) -> Path:
    scrapy = venv_scrapy(qd_dir)
    if not scrapy.exists():
        pc.err("venv não encontrado — execute: make spider-setup")
    return scrapy


def cmd_list(args: argparse.Namespace) -> None:
    qd_dir = args.qd_dir
    scrapy = _require_venv(qd_dir)
    pc.run([str(scrapy), "list"], cwd=str(data_collection_dir(qd_dir)))


def _load_local_env(dc_dir: Path) -> dict:
    env_file = dc_dir / ".local.env"
    env = dict(os.environ)
    if not env_file.exists():
        return env
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _cluster_service_reachable(svc: str) -> bool:
    return pc.run_ok(["kubectl", "get", "svc", svc, "-n", NAMESPACE])


def _auto_database_env() -> dict | None:
    user = pc.get_secret_value("app-secret", "QD_DATA_DB_USER", NAMESPACE)
    password = pc.get_secret_value("app-secret", "QD_DATA_DB_PASSWORD", NAMESPACE)
    if not user or not password:
        return None
    return {
        "QUERIDODIARIO_DATABASE_URL": (
            f"postgresql://{user}:{password}@localhost:{POSTGRES_FORWARD_PORT}/{GAZETTES_DB}"
        ),
    }


def _auto_storage_env() -> dict | None:
    key = pc.get_secret_value("app-secret", "STORAGE_ACCESS_KEY", NAMESPACE)
    secret = pc.get_secret_value("app-secret", "STORAGE_ACCESS_SECRET", NAMESPACE)
    bucket = pc.get_secret_value("app-secret", "STORAGE_BUCKET", NAMESPACE)
    if not key or not secret or not bucket:
        return None
    return {
        "AWS_ACCESS_KEY_ID": key,
        "AWS_SECRET_ACCESS_KEY": secret,
        "AWS_ENDPOINT_URL": f"http://localhost:{GARAGE_S3_FORWARD_PORT}",
        "AWS_REGION_NAME": GARAGE_REGION,
        "FILES_STORE": f"s3://{bucket}/",
    }


# (rótulo, variável que indica config manual já presente, serviço k8s,
#  porta local do port-forward, porta remota, builder das env vars)
AUTO_CONNECTORS = [
    ("Postgres", "QUERIDODIARIO_DATABASE_URL", POSTGRES_SVC, POSTGRES_FORWARD_PORT, 5432, _auto_database_env),
    ("Garage (S3)", "FILES_STORE", GARAGE_SVC, GARAGE_S3_FORWARD_PORT, GARAGE_S3_REMOTE_PORT, _auto_storage_env),
]


def _run_scrapy(cmd: list, dc_dir: Path, env: dict) -> None:
    """Roda um comando scrapy, conectando automaticamente aos serviços do
    cluster kind local (Postgres, Garage/S3) via port-forward temporário,
    pra cada um cuja env var indicadora ainda não estiver configurada — seja
    em `.local.env`, seja no ambiente. Configuração manual sempre tem
    prioridade (ex: pra apontar pra outro ambiente, como o Revoada)."""
    with ExitStack() as stack:
        for label, marker_key, svc, local_port, remote_port, env_builder in AUTO_CONNECTORS:
            if env.get(marker_key):
                continue
            if not _cluster_service_reachable(svc):
                pc.info(
                    f"Cluster kind local não encontrado (svc/{svc}) — rodando sem conexão "
                    f"automática ao {label}. Configure {marker_key} em .local.env se precisar "
                    "apontar pra outro ambiente."
                )
                continue
            extra_env = env_builder()
            if not extra_env:
                pc.warn(f"Não consegui ler credenciais do secret app-secret pra {label} — pulando auto-conexão.")
                continue
            pc.info(f"Conectando automaticamente ao {label} do cluster local (svc/{svc})...")
            stack.enter_context(pc.PortForward(svc, local_port, remote_port, NAMESPACE))
            env.update(extra_env)

        pc.run(cmd, cwd=str(dc_dir), env=env)


def _spider_requires_zyte(dc_dir: Path, spider_name: str) -> bool:
    """Alguns spiders setam `zyte_smartproxy_enabled = True` pra contornar
    proteção anti-bot em sites específicos, exigindo uma API key real do
    Zyte Smart Proxy (serviço pago) — sem ela, `ZYTE_SMARTPROXY_APIKEY` fica
    no placeholder hardcoded em settings.py (não configurável via
    .local.env) e toda requisição falha com "Proxy Authentication Required"."""
    matches = list((dc_dir / "gazette" / "spiders").rglob(f"{spider_name}.py"))
    if not matches:
        return False
    try:
        return "zyte_smartproxy_enabled = True" in matches[0].read_text(encoding="utf-8")
    except OSError:
        return False


def cmd_run(args: argparse.Namespace) -> None:
    if not args.spider:
        pc.err("defina SPIDER=<nome>   ex: make run-spider SPIDER=sp_sao_bernardo_do_campo START=2025-01-01")
    qd_dir = args.qd_dir
    scrapy = _require_venv(qd_dir)
    dc_dir = data_collection_dir(qd_dir)
    env = _load_local_env(dc_dir)

    if _spider_requires_zyte(dc_dir, args.spider):
        pc.warn(
            f"'{args.spider}' usa zyte_smartproxy_enabled=True (proteção anti-bot do site). "
            "ZYTE_SMARTPROXY_APIKEY é um placeholder hardcoded em settings.py, sem suporte a "
            ".local.env — sem uma API key real do Zyte, as requisições vão falhar com "
            "'Proxy Authentication Required'. Isso é uma limitação do repo querido-diario, "
            "não do ambiente local."
        )

    cmd = [str(scrapy), "crawl", args.spider]
    if args.start:
        cmd += ["-a", f"start={args.start}"]
    if args.end:
        cmd += ["-a", f"end={args.end}"]

    _run_scrapy(cmd, dc_dir, env)


def main() -> None:
    # --qd-dir vive num parser "pai" compartilhado pelos subcomandos, para
    # poder ser passado tanto antes quanto depois do subcomando
    # (`spider.py run nome --qd-dir X` e `spider.py --qd-dir X run nome`).
    qd_dir_parser = argparse.ArgumentParser(add_help=False)
    qd_dir_parser.add_argument(
        "--qd-dir",
        type=Path,
        default=Path(os.environ.get("QD_DIR", DEFAULT_QD_DIR)),
        help="Caminho para o repositório querido-diario (raspadores)",
    )

    parser = argparse.ArgumentParser(description=__doc__, parents=[qd_dir_parser])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="Cria venv e instala dependências", parents=[qd_dir_parser])
    sub.add_parser("list", help="Lista os raspadores disponíveis", parents=[qd_dir_parser])

    run_parser = sub.add_parser("run", help="Executa um raspador", parents=[qd_dir_parser])
    run_parser.add_argument("spider")
    run_parser.add_argument("--start", default=None)
    run_parser.add_argument("--end", default=None)

    args = parser.parse_args()
    args.qd_dir = args.qd_dir.resolve()

    {"setup": cmd_setup, "list": cmd_list, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    main()
