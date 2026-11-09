"""Coletor de projetos git: parados com build pesado ou trabalho sem push, e repos fora de dev.

Só lê. Nunca apaga e só roda comandos git de leitura (ADR-0001).
"""

import logging
import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from antilixo.dominio.modelo import Achado, Categoria

logger = logging.getLogger(__name__)

_DIAS_PARADO = 60
_GB = 1_000_000_000  # decimal, como o Finder; mesmo formato do relatorio/markdown.py
_MB = 1_000_000
_TIMEOUT_GIT_S = 30
_BUILD_SEMPRE = frozenset({"node_modules", ".venv", "venv"})
# target/ e .build/ são nomes comuns demais: só contam ao lado do manifesto que os gera.
_BUILD_COM_MANIFESTO = {"target": "Cargo.toml", ".build": "Package.swift"}
# Só no primeiro nível do HOME: dados de app e lixeira não são projetos.
_NO_HOME = frozenset({"Library", ".Trash"})


class RepoIlegivelError(RuntimeError):
    """Um comando git de leitura não rodou no repo (git ausente, repo corrompido, timeout)."""


@dataclass(frozen=True, slots=True)
class _Git:
    executavel: str

    def ler(self, repo: Path, *args: str) -> str:
        """Roda um comando git só de leitura no repo e devolve o stdout."""
        comando = [
            self.executavel,
            # Sem isso, `git status` regrava o índice: o coletor só lê.
            "--no-optional-locks",
            # Explícitos: com `-C` sozinho, um .git corrompido faria o git subir até um repo pai
            # (ex.: HOME versionado com dotfiles) e ler o repo errado.
            f"--git-dir={repo / '.git'}",
            f"--work-tree={repo}",
            "-C",
            str(repo),
            *args,
        ]
        try:
            saida = subprocess.run(  # noqa: S603  # motivo: argumentos fixos, comandos git só de leitura
                comando, check=False, capture_output=True, text=True, timeout=_TIMEOUT_GIT_S
            )
        except (OSError, subprocess.TimeoutExpired) as erro:
            msg = f"{' '.join(comando)} não rodou ({erro}); esperado git em {self.executavel!r}"
            raise RepoIlegivelError(msg) from erro
        if saida.returncode != 0:
            erro = saida.stderr.strip()
            msg = f"{' '.join(comando)} saiu com {saida.returncode}, esperado 0: {erro}"
            raise RepoIlegivelError(msg)
        return saida.stdout


@dataclass(frozen=True, slots=True)
class _Situacao:
    dias_parado: int | None  # None: sem commit nem arquivo rastreado, não há como datar
    builds: tuple[tuple[str, int], ...]  # (nome da pasta, bytes somados), do maior ao menor
    commits_sem_push: int
    stashes: int
    arquivos_nao_salvos: int

    @property
    def build_bytes(self) -> int:
        return sum(tamanho for _, tamanho in self.builds)

    @property
    def nao_salvo(self) -> bool:
        return bool(self.commits_sem_push or self.stashes or self.arquivos_nao_salvos)

    @property
    def parado(self) -> bool:
        return (
            self.dias_parado is not None
            and self.dias_parado > _DIAS_PARADO
            and bool(self.build_bytes or self.nao_salvo)
        )


def coletar_projetos(home: Path, dev: Path, hoje: date, *, git: str = "git") -> tuple[Achado, ...]:
    """Achados de PROJETO_PARADO e GIT_FORA_DE_DEV para os repos sob `home`.

    `git` existe para o teste simular git ausente. Repo ilegível é pulado e fica no log.
    """
    executor = _Git(git)
    achados: list[Achado] = []
    for repo in _achar_repos(home):
        try:
            achados.extend(_achados_do_repo(repo, home, dev, hoje, executor))
        except (RepoIlegivelError, OSError) as erro:
            logger.warning("repo pulado: %s: %s", repo, erro)
    return tuple(achados)


def _achados_do_repo(repo: Path, home: Path, dev: Path, hoje: date, git: _Git) -> list[Achado]:
    """Tudo ou nada: se o git falhar no meio, o repo não gera achado nenhum."""
    achados: list[Achado] = []
    situacao = _ler_situacao(repo, hoje, git)
    if situacao.parado:
        motivo = _motivo(situacao)
        achados.append(Achado(Categoria.PROJETO_PARADO, repo, situacao.build_bytes, motivo))
    if not repo.is_relative_to(dev):
        motivo = f"repositório git fora de {_exibir(dev, home)}"
        achados.append(Achado(Categoria.GIT_FORA_DE_DEV, repo, _tamanho(repo), motivo))
    return achados


def _ler_situacao(repo: Path, hoje: date, git: _Git) -> _Situacao:
    stashes, arquivos_nao_salvos = _status(repo, git)
    ultima = _ultima_atividade(repo, git)
    return _Situacao(
        dias_parado=None if ultima is None else (hoje - ultima).days,
        builds=_medir_build(repo),
        commits_sem_push=_commits_sem_push(repo, git),
        stashes=stashes,
        arquivos_nao_salvos=arquivos_nao_salvos,
    )


def _motivo(situacao: _Situacao) -> str:
    partes = [f"parado há {situacao.dias_parado} dias"]
    partes.extend(f"{_formatar_tamanho(tamanho)} em {nome}" for nome, tamanho in situacao.builds)
    if situacao.commits_sem_push:
        partes.append(_plural(situacao.commits_sem_push, "commit sem push", "commits sem push"))
    if situacao.stashes:
        partes.append(_plural(situacao.stashes, "stash", "stashes"))
    if situacao.arquivos_nao_salvos:
        partes.append(
            _plural(
                situacao.arquivos_nao_salvos,
                "arquivo modificado ou não rastreado",
                "arquivos modificados ou não rastreados",
            )
        )
    return "; ".join(partes)


def _exibir(caminho: Path, home: Path) -> str:
    return f"~/{caminho.relative_to(home)}" if caminho.is_relative_to(home) else str(caminho)


def _formatar_tamanho(tamanho_bytes: int) -> str:
    if tamanho_bytes >= _GB:
        return f"{tamanho_bytes / _GB:.1f} GB".replace(".", ",")
    return f"{tamanho_bytes // _MB} MB"


def _plural(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _achar_repos(home: Path) -> Iterator[Path]:
    """Repos sob `home`, sem seguir symlinks e sem descer em lixo conhecido nem dentro de repo."""
    pendentes = [home]
    while pendentes:
        pasta = pendentes.pop()
        try:
            with os.scandir(pasta) as entradas:
                subpastas = sorted(
                    Path(e.path) for e in entradas if e.is_dir(follow_symlinks=False)
                )
        except OSError as erro:
            # Pasta protegida (TCC do macOS, permissão): perde-se só ela, não a coleta.
            logger.warning("pasta pulada: %s: %s", pasta, erro)
            continue
        for subpasta in reversed(subpastas):
            if subpasta.name in _BUILD_SEMPRE or (pasta == home and subpasta.name in _NO_HOME):
                continue
            if (subpasta / ".git").exists(follow_symlinks=False):
                yield subpasta
            else:
                pendentes.append(subpasta)


def _medir_build(repo: Path) -> tuple[tuple[str, int], ...]:
    """Bytes das pastas de build recriáveis em qualquer nível do repo, somados por nome."""
    por_nome: dict[str, int] = {}
    for pasta, subpastas, _ in repo.walk():
        for nome in list(subpastas):
            if nome == ".git":
                subpastas.remove(nome)
            elif _e_build(pasta, nome):
                subpastas.remove(nome)  # medido inteiro: não desce de novo
                por_nome[nome] = por_nome.get(nome, 0) + _tamanho(pasta / nome)
    return tuple(sorted(por_nome.items(), key=lambda item: (-item[1], item[0])))


def _e_build(pasta: Path, nome: str) -> bool:
    if nome in _BUILD_SEMPRE:
        return True
    manifesto = _BUILD_COM_MANIFESTO.get(nome)
    return manifesto is not None and (pasta / manifesto).is_file()


def _tamanho(raiz: Path) -> int:
    """Bytes aparentes (st_size) dos arquivos sob `raiz`, sem seguir symlinks."""
    total = 0
    for pasta, _, arquivos in raiz.walk():
        total += sum((pasta / nome).lstat().st_size for nome in arquivos)
    return total


def _ultima_atividade(repo: Path, git: _Git) -> date | None:
    """O mais recente entre o último commit e o mtime dos arquivos rastreados."""
    # De todas as branches locais, não só do HEAD: trabalho numa branch lateral também é atividade.
    commits = git.ler(repo, "for-each-ref", "--format=%(committerdate:unix)", "refs/heads")
    instantes = [int(linha) for linha in commits.split()]
    rastreados = (repo / r for r in git.ler(repo, "ls-files", "-z").split("\0") if r)
    # Rastreado e apagado do disco já conta em _status; aqui não tem mtime.
    instantes.extend(
        int(arquivo.lstat().st_mtime)
        for arquivo in rastreados
        if arquivo.exists(follow_symlinks=False)
    )
    if not instantes:
        return None
    return datetime.fromtimestamp(max(instantes), tz=UTC).astimezone().date()


def _commits_sem_push(repo: Path, git: _Git) -> int:
    """Commits de branches locais que nenhum ref remoto alcança (à frente ou sem upstream)."""
    return int(git.ler(repo, "rev-list", "--count", "--branches", "--not", "--remotes"))


def _status(repo: Path, git: _Git) -> tuple[int, int]:
    """Stashes e arquivos modificados, apagados ou não rastreados (ignorados não contam).

    Uma chamada só: o cabeçalho `# stash N` do porcelain v2 poupa um `git stash list` por repo.
    """
    saida = git.ler(
        repo, "status", "--porcelain=v2", "--show-stash", "--no-renames", "--untracked-files=normal"
    )
    stashes = 0
    arquivos = 0
    for linha in saida.splitlines():
        if linha.startswith("# stash "):
            stashes = int(linha.removeprefix("# stash "))
        elif not linha.startswith("#"):
            arquivos += 1
    return stashes, arquivos
