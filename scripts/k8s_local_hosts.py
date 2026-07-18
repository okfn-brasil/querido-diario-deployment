#!/usr/bin/env python3
"""k8s_local_hosts.py — Adiciona as entradas *.queridodiario.local ao hosts
file local (idempotente: pula entradas que já existem).

Linux/macOS: /etc/hosts, requer sudo.
Windows: C:\\Windows\\System32\\drivers\\etc\\hosts, requer terminal
executado "Como Administrador".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

HOSTS = [
    "queridodiario.local",
    "api.queridodiario.local",
    "backend-api.queridodiario.local",
]


def hosts_path() -> Path:
    if pc.IS_WINDOWS:
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")


def main() -> None:
    path = hosts_path()
    try:
        current = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        pc.err(f"Não foi possível ler {path}: {e}")

    missing = [h for h in HOSTS if h not in current]
    if not missing:
        pc.info("Entradas já presentes no hosts file.")
        return

    lines = "".join(f"127.0.0.1  {h}\n" for h in missing)

    # Tenta escrever diretamente (funciona se já rodando com privilégios).
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
        pc.log("Entradas adicionadas ao hosts file.")
        return
    except PermissionError:
        pass

    if pc.IS_WINDOWS:
        pc.err(
            "Permissão negada ao escrever no hosts file.\n"
            "  Abra um terminal 'Como Administrador' e rode novamente:\n"
            "    make k8s-local-hosts\n"
            "  Ou adicione manualmente estas linhas em "
            f"{path}:\n" + "".join(f"    127.0.0.1  {h}\n" for h in missing)
        )

    # Linux/macOS: usa sudo tee (pede senha interativamente).
    if not pc.which("sudo"):
        pc.err(
            f"Permissão negada ao escrever em {path} e 'sudo' não encontrado.\n"
            "Adicione manualmente:\n" + "".join(f"    127.0.0.1  {h}\n" for h in missing)
        )

    pc.info("Permissão de root necessária — solicitando via sudo...")
    proc = pc.subprocess.run(["sudo", "tee", "-a", str(path)], input=lines, text=True, stdout=pc.subprocess.DEVNULL)
    if proc.returncode != 0:
        pc.err("Falha ao escrever no hosts file via sudo.")
    pc.log("Entradas adicionadas ao hosts file.")


if __name__ == "__main__":
    main()
