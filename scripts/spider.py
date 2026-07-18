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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

DEFAULT_QD_DIR = pc.REPO_ROOT.parent / "querido-diario"


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


def cmd_setup(args: argparse.Namespace) -> None:
    qd_dir = args.qd_dir
    dc_dir = data_collection_dir(qd_dir)
    requirements = dc_dir / "requirements.txt"
    if not requirements.exists():
        pc.err(f"requirements.txt não encontrado em {requirements} — confira QD_DIR.")

    python_bin = pc.which("python3") or pc.which("python") or sys.executable
    pc.log(f"Criando venv em {venv_dir(qd_dir)}...")
    pc.run([python_bin, "-m", "venv", str(venv_dir(qd_dir))])

    pip = venv_bin(qd_dir) / pc.exe("pip")
    pc.run([str(pip), "install", "--upgrade", "pip"])
    pc.run([str(pip), "install", "-r", str(requirements)])
    pc.log("Ambiente dos raspadores pronto.")


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


def cmd_run(args: argparse.Namespace) -> None:
    if not args.spider:
        pc.err("defina SPIDER=<nome>   ex: make run-spider SPIDER=sp_campinas START=2025-01-01")
    qd_dir = args.qd_dir
    scrapy = _require_venv(qd_dir)
    dc_dir = data_collection_dir(qd_dir)
    env = _load_local_env(dc_dir)

    cmd = [str(scrapy), "crawl", args.spider]
    if args.start:
        cmd += ["-a", f"start={args.start}"]
    if args.end:
        cmd += ["-a", f"end={args.end}"]

    pc.run(cmd, cwd=str(dc_dir), env=env)


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
