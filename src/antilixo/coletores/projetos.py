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

from antilixo.coletores.nao_lidas import caminho_do_erro, resumir_pastas_nao_lidas
from antilixo.dominio.modelo import Achado, Categoria, Leitura
from antilixo.dominio.tamanho import formatar_tamanho

logger = logging.getLogger(__name__)

_DIAS_PARADO = 60
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
    # Pares `-c chave=valor` que anulam o que a config do repo executaria (ver _abrir).
    neutros: tuple[str, ...] = ()

    def ler(self, repo: Path, *args: str, vazio_sai_com_1: bool = False) -> str:
        """Roda um comando git só de leitura no repo e devolve o stdout.

        `vazio_sai_com_1`: sai com 1 quando não acha nada (ex.: `git config --get-regexp`).
        """
        comando = [
            self.executavel,
            # Sem tty não há pager; explícito para `core.pager` do repo nunca entrar em jogo.
            "--no-pager",
            # Sem isso, `git status` regrava o índice: o coletor só lê.
            "--no-optional-locks",
            # Repo hostil no HOME (achado S1, 2026-11-09): o fsmonitor da config local roda comando
            # a cada `git status`. `-c` na linha de comando vence a config do repo.
            "-c",
            "core.fsmonitor=false",
            *self.neutros,
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
        if saida.returncode == 1 and vazio_sai_com_1 and not saida.stdout:
            return ""
        if saida.returncode != 0:
            erro = saida.stderr.strip()
            msg = f"{' '.join(comando)} saiu com {saida.returncode}, esperado 0: {erro}"
            raise RepoIlegivelError(msg)
        return saida.stdout


def _abrir(executavel: str, repo: Path) -> _Git:
    """Git para ler `repo` com todo filtro da config anulado.

    Filtro (`filter.<nome>.clean`/`process`) é comando que o `git status` roda ao reler um arquivo,
    ativado por `.gitattributes` ou `.git/info/attributes` (achado S1, opção (b) decidida pelo
    humano em 2026-11-09). Nenhuma bandeira do git desliga todos; por isso cada nome configurado é
    anulado. Ler os nomes com `git config` não executa nada.
    """
    chaves = _Git(executavel).ler(
        repo, "config", "-z", "--name-only", "--get-regexp", r"^filter\.", vazio_sai_com_1=True
    )
    # `filter.a.b.clean` é o filtro "a.b": o nome é tudo entre o primeiro e o último ponto.
    nomes = sorted({c.removeprefix("filter.").rpartition(".")[0] for c in chaves.split("\0") if c})
    # `-c` corta chave e valor no primeiro "=": um filtro "a=b" não tem como ser anulado e
    # executaria (achado da code-audit de 2026-11-09). Fecha por falha: o repo é pulado.
    inanulaveis = [nome for nome in nomes if "=" in nome]
    if inanulaveis:
        msg = f"filtro {inanulaveis} em {repo}: nome com '=' não é anulável; esperado nome sem '='"
        raise RepoIlegivelError(msg)
    neutros: list[str] = []
    for nome in nomes:
        for chave in ("clean=", "smudge=", "process=", "required=false"):
            neutros.extend(("-c", f"filter.{nome}.{chave}"))
    return _Git(executavel, tuple(neutros))


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


def coletar_projetos(home: Path, dev: Path, hoje: date, *, git: str = "git") -> Leitura:
    """Achados de PROJETO_PARADO e GIT_FORA_DE_DEV para os repos sob `home`.

    `git` existe para o teste simular git ausente. Repo ilegível é pulado e fica no log.
    """
    achados: list[Achado] = []
    erros: list[OSError] = []
    for repo in _achar_repos(home, erros):
        try:
            achados.extend(_achados_do_repo(repo, home, dev, hoje, _abrir(git, repo)))
        except (RepoIlegivelError, OSError) as erro:
            logger.warning("repo pulado: %s: %s", repo, erro)
    nao_lidas = _resumir_por_pasta_do_home(home, erros)
    for linha in nao_lidas:
        logger.warning("não lido: %s", linha)
    return Leitura(tuple(achados), nao_lidas)


def _resumir_por_pasta_do_home(home: Path, erros: list[OSError]) -> tuple[str, ...]:
    """Uma linha por pasta do primeiro nível do HOME (~/Documents, ~/Desktop), em ordem.

    Pasta bloqueada (TCC do macOS, permissão) perde só os repos dela, mas o relatório precisa
    dizer que ela não foi lida (achado da revisão de 2026-11-09).
    """
    por_pasta: dict[Path, list[OSError]] = {}
    for erro in erros:
        caminho = caminho_do_erro(erro)
        dentro = caminho is not None and caminho != home and caminho.is_relative_to(home)
        raiz = home / caminho.relative_to(home).parts[0] if caminho and dentro else home
        por_pasta.setdefault(raiz, []).append(erro)
    return tuple(
        linha
        for raiz in sorted(por_pasta)
        for linha in resumir_pastas_nao_lidas(_exibir(raiz, home), raiz, por_pasta[raiz])
    )


def _achados_do_repo(repo: Path, home: Path, dev: Path, hoje: date, git: _Git) -> list[Achado]:
    """Tudo ou nada: se o git falhar no meio, o repo não gera achado nenhum."""
    achados: list[Achado] = []
    situacao = _ler_situacao(repo, hoje, git)
    if situacao.parado:
        motivo = _motivo(situacao)
        achados.append(Achado(Categoria.PROJETO_PARADO, repo, situacao.build_bytes, motivo))
    if not repo.is_relative_to(dev):
        motivo = f"repositório git fora de {_exibir(dev, home)}"
        achados.append(Achado(Categoria.GIT_FORA_DE_DEV, repo, _tamanho(repo, set()), motivo))
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
    partes.extend(f"{formatar_tamanho(tamanho)} em {nome}" for nome, tamanho in situacao.builds)
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


def _plural(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _achar_repos(home: Path, erros: list[OSError]) -> Iterator[Path]:
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
            # Pasta protegida (TCC do macOS, permissão): perde-se só ela, não a coleta. O erro
            # vai resumido para o log e para o relatório, e não uma linha por pasta.
            erros.append(erro)
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
    vistos: set[tuple[int, int]] = set()  # um achado: hardlink entre builds conta uma vez
    for pasta, subpastas, _ in repo.walk():
        subpastas.sort()  # ordem fixa: o hardlink compartilhado cai sempre no mesmo nome
        builds = [nome for nome in subpastas if nome != ".git" and _e_build(pasta, nome)]
        for nome in builds:
            por_nome[nome] = por_nome.get(nome, 0) + _tamanho(pasta / nome, vistos)
        # Poda do walk sem list.remove (o teste de arquitetura lê `remove` como apagar): não desce
        # no .git nem num build já medido inteiro.
        subpastas[:] = [nome for nome in subpastas if nome != ".git" and nome not in builds]
    return tuple(sorted(por_nome.items(), key=lambda item: (-item[1], item[0])))


def _e_build(pasta: Path, nome: str) -> bool:
    if nome in _BUILD_SEMPRE:
        return True
    manifesto = _BUILD_COM_MANIFESTO.get(nome)
    return manifesto is not None and (pasta / manifesto).is_file()


def _tamanho(raiz: Path, vistos: set[tuple[int, int]]) -> int:
    """Espaço ocupado no disco pelos arquivos sob `raiz`, sem seguir symlinks.

    st_blocks * 512, não st_size (decisão de 2026-11-09): arquivo esparso conta o que aloca.
    Hardlink conta uma vez por inode; `vistos` é compartilhado por todo o achado.
    """
    total = 0
    for pasta, _, arquivos in raiz.walk():
        for nome in arquivos:
            info = (pasta / nome).lstat()
            inode = (info.st_dev, info.st_ino)
            if inode not in vistos:
                vistos.add(inode)
                total += info.st_blocks * 512
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
        repo,
        "status",
        "--porcelain=v2",
        "--show-stash",
        "--no-renames",
        "--untracked-files=normal",
        # Sem descer no submódulo: a config dele tem filtros que _abrir não anula (achado S1).
        # Perde-se a sujeira dentro do submódulo; o commit dele trocado continua aparecendo.
        "--ignore-submodules=dirty",
    )
    stashes = 0
    arquivos = 0
    for linha in saida.splitlines():
        if linha.startswith("# stash "):
            stashes = int(linha.removeprefix("# stash "))
        elif not linha.startswith("#"):
            arquivos += 1
    return stashes, arquivos
