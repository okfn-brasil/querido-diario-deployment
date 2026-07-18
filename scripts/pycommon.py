"""Helpers compartilhados pelos scripts de automação (Linux/Mac/Windows).

Só usa a biblioteca padrão do Python (nenhuma dependência externa) para que
os scripts rodem em qualquer máquina com Python 3.9+ instalado, sem exigir
`pip install` antes de tocar em nada.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

REPO_ROOT = Path(__file__).resolve().parent.parent

# Diretório local para binários auto-instalados (kubectl/kind/helm).
# Mesmo caminho em todos os SOs: só uma pasta dentro do home do usuário.
LOCAL_BIN = Path.home() / ".local" / "bin"


# ─── Saída colorida ────────────────────────────────────────────────────────

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if IS_WINDOWS:
        # Terminais modernos do Windows (10+) suportam ANSI, mas precisa
        # habilitar o modo explicitamente via uma chamada ao console.
        try:
            os.system("")
        except Exception:
            return False
    return True


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def log(msg: str) -> None:
    print(f"{_c('0;32', '[setup]')} {msg}")


def info(msg: str) -> None:
    print(f"{_c('0;34', '[info]')}  {msg}")


def warn(msg: str) -> None:
    print(f"{_c('1;33', '[warn]')}  {msg}")


def err(msg: str) -> None:
    print(f"{_c('0;31', '[erro]')}  {msg}", file=sys.stderr)
    sys.exit(1)


# ─── Execução de comandos ──────────────────────────────────────────────────

def run(cmd: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    """Executa um comando, propagando stdout/stderr, e falha em erro (exceto se check=False)."""
    kwargs.setdefault("check", True)
    return subprocess.run(list(cmd), **kwargs)


def run_ok(cmd: Sequence[str]) -> bool:
    """True se o comando existe e roda com código de saída 0 (silencioso)."""
    try:
        subprocess.run(
            list(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def capture(cmd: Sequence[str]) -> str | None:
    """Roda um comando e retorna stdout (str) ou None se falhar."""
    try:
        proc = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
        )
        return proc.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def which(name: str) -> str | None:
    return shutil.which(name)


def find_python(preferred_versions: Sequence[str], fallback: bool = True) -> str:
    """Procura um interpretador Python numa lista de versões preferidas
    (ex: ["3.10", "3.11", "3.12"], na ordem de preferência), útil quando um
    projeto irmão tem dependências antigas sem wheel pra versão atual do
    `python3` do PATH (comum com pacotes C como lxml em versões pinadas).

    Procura primeiro versões instaladas via pyenv (~/.pyenv/versions/X.Y.Z/
    bin/python3), depois um binário `pythonX.Y` direto no PATH. Se nada bater
    e fallback=True, retorna o `python3`/`python` padrão do PATH.
    """
    pyenv_root = Path(os.environ.get("PYENV_ROOT", Path.home() / ".pyenv"))
    pyenv_versions_dir = pyenv_root / "versions"

    for version in preferred_versions:
        if pyenv_versions_dir.is_dir():
            candidates = sorted(
                (d for d in pyenv_versions_dir.iterdir() if d.is_dir() and d.name.startswith(f"{version}.")),
                reverse=True,
            )
            for candidate_dir in candidates:
                python_bin = candidate_dir / "bin" / exe("python3")
                if python_bin.exists():
                    return str(python_bin)

        direct = which(f"python{version}")
        if direct:
            return direct

    if fallback:
        return which("python3") or which("python") or sys.executable
    err(f"Nenhum Python encontrado entre as versões preferidas: {', '.join(preferred_versions)}")


def ensure_path_has(directory: Path) -> None:
    """Garante que `directory` esteja no PATH do processo atual (e filhos)."""
    directory_str = str(directory)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if directory_str not in parts:
        os.environ["PATH"] = directory_str + os.pathsep + os.environ.get("PATH", "")


# ─── Plataforma / arquitetura ──────────────────────────────────────────────

def os_name() -> str:
    """Nome do SO no formato usado pelos releases de kubectl/kind/helm."""
    system = platform.system()
    return {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(system, system.lower())


def arch_name() -> str:
    """Nome da arquitetura no formato usado pelos releases (amd64/arm64)."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


def exe(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


# ─── Download / instalação de binários ─────────────────────────────────────

def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "querido-diario-deployment"})
    try:
        with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as e:
        err(f"Falha ao baixar {url}: HTTP {e.code}")
    except urllib.error.URLError as e:
        err(f"Falha ao baixar {url}: {e.reason}")


def github_latest_tag(repo: str) -> str:
    """Consulta a tag da última release de um repo GitHub (ex: 'helm/helm')."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "querido-diario-deployment"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
        return data["tag_name"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as e:
        err(f"Não foi possível consultar a última versão de {repo}: {e}")


def install_raw_binary(url: str, bin_name: str) -> Path:
    """Baixa um binário único (sem arquivo compactado) para LOCAL_BIN."""
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    dest = LOCAL_BIN / exe(bin_name)
    log(f"Baixando {bin_name} de {url} ...")
    _download(url, dest)
    if not IS_WINDOWS:
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ensure_path_has(LOCAL_BIN)
    return dest


def install_archive_binary(url: str, bin_name: str, archive_kind: str) -> Path:
    """Baixa um .tar.gz ou .zip, extrai o binário `bin_name` e o copia para LOCAL_BIN."""
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    target_name = exe(bin_name)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / f"download.{archive_kind}"
        log(f"Baixando {bin_name} de {url} ...")
        _download(url, archive_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        if archive_kind == "tar.gz":
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)
        elif archive_kind == "zip":
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        else:
            err(f"Tipo de arquivo desconhecido: {archive_kind}")

        found = list(extract_dir.rglob(target_name))
        if not found:
            err(f"Binário '{target_name}' não encontrado dentro do pacote baixado.")
        dest = LOCAL_BIN / target_name
        shutil.copy2(found[0], dest)

    if not IS_WINDOWS:
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ensure_path_has(LOCAL_BIN)
    return dest


# ─── Ferramentas específicas ────────────────────────────────────────────────

def ensure_kubectl() -> None:
    """Instala o kubectl (versão estável mais recente) se ele não estiver disponível."""
    if which("kubectl"):
        info(f"kubectl ok: {capture(['kubectl', 'version', '--client', '--short']) or capture(['kubectl', 'version', '--client'])}")
        return

    warn("kubectl não encontrado. Instalando automaticamente...")
    req = urllib.request.Request(
        "https://dl.k8s.io/release/stable.txt",
        headers={"User-Agent": "querido-diario-deployment"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            version = resp.read().decode().strip()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        err(f"Não foi possível determinar a versão estável do kubectl: {e}")

    os_, arch = os_name(), arch_name()
    url = f"https://dl.k8s.io/release/{version}/bin/{os_}/{arch}/{exe('kubectl')}"
    install_raw_binary(url, "kubectl")
    info(f"kubectl {version} instalado em {LOCAL_BIN}.")


def _kind_version_tuple(version_output: str | None) -> tuple[int, int, int] | None:
    if not version_output:
        return None
    import re

    m = re.search(r"v(\d+)\.(\d+)\.(\d+)", version_output)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def ensure_kind(min_version: str, install_version: str) -> None:
    """Garante kind >= min_version, instalando install_version se ausente/desatualizado."""
    current = capture(["kind", "version"]) if which("kind") else None
    current_v = _kind_version_tuple(current)
    min_v = _kind_version_tuple(f"v{min_version}")

    if current_v and min_v and current_v >= min_v:
        info(f"kind ok: {current}")
        return

    warn(f"kind desatualizado ou ausente ({current or 'não instalado'}). Mínimo necessário: v{min_version}.")
    os_, arch = os_name(), arch_name()
    url = f"https://kind.sigs.k8s.io/dl/v{install_version}/kind-{os_}-{arch}"
    log(f"Instalando kind v{install_version} em {LOCAL_BIN}...")
    install_raw_binary(url, "kind")
    info(f"kind instalado: {capture(['kind', 'version'])}")


def ensure_helm() -> None:
    """Instala o Helm (versão estável mais recente) se ele não estiver disponível."""
    if which("helm"):
        info(f"helm já instalado: {capture(['helm', 'version', '--short'])}")
        return

    warn("helm não encontrado. Instalando automaticamente...")
    version = github_latest_tag("helm/helm")
    os_, arch = os_name(), arch_name()
    archive_kind = "zip" if IS_WINDOWS else "tar.gz"
    ext = "zip" if IS_WINDOWS else "tar.gz"
    url = f"https://get.helm.sh/helm-{version}-{os_}-{arch}.{ext}"
    install_archive_binary(url, "helm", archive_kind)
    info(f"helm {version} instalado em {LOCAL_BIN}.")


def docker_install_hint() -> str:
    if IS_MACOS:
        return "brew install --cask docker   (ou baixe o Docker Desktop em docker.com)"
    if IS_WINDOWS:
        return "winget install Docker.DockerDesktop   (ou baixe o Docker Desktop em docker.com)"
    return "veja https://docs.docker.com/engine/install/ para o guia da sua distro"


def check_docker() -> None:
    """Verifica se o docker está instalado, com daemon rodando em modo Linux containers."""
    if not which("docker"):
        err(
            "docker não encontrado. A instalação do Docker não é automática "
            f"(requer privilégios/reinício em vários SOs). Instale com:\n    {docker_install_hint()}"
        )

    info_output = capture(["docker", "info", "--format", "{{.OSType}}"])
    if info_output is None:
        err("Docker daemon não está rodando (ou não respondeu). Inicie o Docker e tente novamente.")
    if info_output and info_output.strip() not in ("linux", ""):
        err(
            f"Docker está em modo '{info_output.strip()}', mas o kind requer containers Linux. "
            "No Docker Desktop (Mac/Windows), troque para 'Linux containers'."
        )


def port_in_use(port: int, host: str = "127.0.0.1") -> bool | None:
    """Tenta abrir um socket na porta.

    Retorna True se já estiver em uso, False se estiver livre, ou None se não
    foi possível determinar (ex: porta <1024 sem privilégios para testar via
    bind — comum em Linux/Mac para a porta 80 quando rodando sem root/sudo;
    nesse caso o bind falha com EACCES mesmo que a porta esteja livre).
    """
    import errno

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.bind((host, port))
        except PermissionError:
            return None
        except OSError as e:
            if e.errno == errno.EACCES:
                return None
            return True
        return False


def get_secret_value(secret: str, key: str, namespace: str) -> str | None:
    """Lê e decodifica (base64) uma chave de um Secret do k8s."""
    import base64

    encoded = capture(
        ["kubectl", "get", "secret", secret, "-n", namespace, "-o", f"jsonpath={{.data.{key}}}"]
    )
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 20.0) -> bool:
    """Tenta conectar em host:port repetidamente até timeout. Retorna True se conectou."""
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            try:
                s.connect((host, port))
                return True
            except OSError:
                _time.sleep(0.5)
    return False


class PortForward:
    """Context manager: abre `kubectl port-forward` em background e garante
    que o processo seja encerrado ao sair do bloco `with`, mesmo em erro."""

    def __init__(self, service: str, local_port: int, remote_port: int, namespace: str):
        self.service = service
        self.local_port = local_port
        self.remote_port = remote_port
        self.namespace = namespace
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "PortForward":
        self._proc = subprocess.Popen(
            [
                "kubectl", "port-forward",
                f"svc/{self.service}", f"{self.local_port}:{self.remote_port}",
                "-n", self.namespace,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port(self.local_port):
            self.__exit__(None, None, None)
            err(f"Não foi possível abrir port-forward para svc/{self.service}:{self.remote_port}.")
        return self

    def __exit__(self, *exc_info) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


def path_hint() -> str:
    if IS_WINDOWS:
        return (
            f'Adicione "{LOCAL_BIN}" à variável de ambiente PATH '
            "(Configurações > Variáveis de Ambiente, ou `setx PATH \"%PATH%;" + str(LOCAL_BIN) + "\"`)."
        )
    shell_rc = "~/.zshrc" if os.environ.get("SHELL", "").endswith("zsh") else "~/.bashrc"
    return f'Adicione a linha `export PATH="{LOCAL_BIN}:$PATH"` ao seu {shell_rc}.'
