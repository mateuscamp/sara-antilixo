"""Coletor de projetos git. Repos reais criados com `git` em `tmp_path`; nunca toca o HOME real."""

import logging
import os
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from antilixo.coletores.projetos import coletar_projetos
from antilixo.dominio.modelo import Achado, Categoria

HOJE = date(2026, 11, 9)
IDADE_DO_MODELO = 100
_GIT = shutil.which("git") or "git-ausente-no-path"


def _instante(dias_atras: int) -> datetime:
    return datetime(HOJE.year, HOJE.month, HOJE.day, 12, tzinfo=UTC) - timedelta(days=dias_atras)


def _git(repo: Path, *args: str, dias_atras: int = 0) -> str:
    # Ambiente montado do zero: sem config global do usuário (gpgsign, hooks) e com datas fixas.
    quando = _instante(dias_atras).isoformat()
    ambiente = {
        "HOME": str(repo),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Teste",
        "GIT_AUTHOR_EMAIL": "teste@example.com",
        "GIT_COMMITTER_NAME": "Teste",
        "GIT_COMMITTER_EMAIL": "teste@example.com",
        "GIT_AUTHOR_DATE": quando,
        "GIT_COMMITTER_DATE": quando,
    }
    saida = subprocess.run(  # noqa: S603  # motivo: git do PATH com argumentos fixos do teste
        [_GIT, "-C", str(repo), *args], env=ambiente, check=True, capture_output=True, text=True
    )
    return saida.stdout


def _escrever(caminho: Path, conteudo: bytes, *, dias_atras: int = 0) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    _ = caminho.write_bytes(conteudo)
    instante = _instante(dias_atras).timestamp()
    os.utime(caminho, (instante, instante))
    return caminho


def _commitar(repo: Path, nome: str, *, dias_atras: int) -> None:
    _ = _escrever(repo / nome, nome.encode(), dias_atras=dias_atras)
    _ = _git(repo, "add", nome)
    _ = _git(repo, "commit", "--quiet", "-m", nome, dias_atras=dias_atras)


@pytest.fixture(scope="session")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """HOME falso com `dev/app` publicado em `remotos/app.git`, limpo, parado há 100 dias.

    Criado uma vez e copiado por teste: processo git custa caro e a suíte tem de ficar <10 s.
    O remoto vai por caminho relativo para cada cópia empurrar no seu próprio remoto.
    """
    raiz = tmp_path_factory.mktemp("modelo")
    remoto = raiz / "remotos" / "app.git"
    remoto.mkdir(parents=True)
    _ = _git(remoto, "init", "--quiet", "--bare", "--initial-branch=main")
    repo = raiz / "dev" / "app"
    repo.mkdir(parents=True)
    _ = _git(repo, "init", "--quiet", "--initial-branch=main")
    _ = _escrever(repo / "README.md", b"# projeto\n", dias_atras=IDADE_DO_MODELO)
    # Build ignorado, como num projeto real: senão contaria como arquivo não rastreado.
    ignorados = b"node_modules/\n.venv/\nvenv/\ntarget/\n.build/\n"
    _ = _escrever(repo / ".gitignore", ignorados, dias_atras=IDADE_DO_MODELO)
    _ = _git(repo, "add", "README.md", ".gitignore")
    _ = _git(repo, "commit", "--quiet", "-m", "inicio", dias_atras=IDADE_DO_MODELO)
    _ = _git(repo, "remote", "add", "origin", "../../remotos/app.git")
    _ = _git(repo, "push", "--quiet", "--set-upstream", "origin", "main")
    return raiz


@pytest.fixture
def home(tmp_path: Path, modelo: Path) -> Path:
    destino = tmp_path / "home"
    _ = shutil.copytree(modelo, destino, symlinks=True)
    return destino


def _da_categoria(achados: tuple[Achado, ...], categoria: Categoria) -> list[Achado]:
    return [a for a in achados if a.categoria is categoria]


def _parados(home: Path) -> list[Achado]:
    return _da_categoria(coletar_projetos(home, home / "dev", HOJE), Categoria.PROJETO_PARADO)


def test_repo_parado_com_node_modules_vira_projeto_parado_com_o_tamanho_do_build(
    home: Path,
) -> None:
    repo = home / "dev" / "app"
    _ = _escrever(repo / "node_modules" / "pacote" / "index.js", b"x" * 1500)
    _ = _escrever(repo / "node_modules" / "outro.js", b"x" * 500)

    assert [(a.caminho, a.tamanho_bytes) for a in _parados(home)] == [(repo, 2000)]


def test_arquivo_rastreado_editado_recentemente_conta_como_atividade(home: Path) -> None:
    repo = home / "dev" / "app"
    _ = _escrever(repo / "node_modules" / "index.js", b"x" * 100)
    _ = _escrever(repo / "README.md", b"# projeto\n", dias_atras=10)

    assert _parados(home) == []


def test_commits_a_frente_do_upstream_sao_trabalho_nao_salvo(home: Path) -> None:
    repo = home / "dev" / "app"
    _commitar(repo, "a.txt", dias_atras=95)
    _commitar(repo, "b.txt", dias_atras=92)

    assert [(a.caminho, a.tamanho_bytes, a.motivo) for a in _parados(home)] == [
        (repo, 0, "parado há 92 dias; 2 commits sem push")
    ]


def test_repo_parado_publicado_e_limpo_sem_build_nao_e_achado(home: Path) -> None:
    assert _parados(home) == []


def test_branch_local_sem_upstream_com_commit_conta_como_sem_push(home: Path) -> None:
    repo = home / "dev" / "app"
    _ = _git(repo, "switch", "--quiet", "--create", "experimento")
    _commitar(repo, "a.txt", dias_atras=90)
    _ = _git(repo, "switch", "--quiet", "main")

    assert [a.motivo for a in _parados(home)] == ["parado há 90 dias; 1 commit sem push"]


def test_stash_e_trabalho_nao_salvo(home: Path) -> None:
    repo = home / "dev" / "app"
    _ = _escrever(repo / "README.md", b"rascunho\n")
    _ = _git(repo, "stash", "push", "--quiet", dias_atras=IDADE_DO_MODELO)
    _ = _escrever(repo / "README.md", b"# projeto\n", dias_atras=IDADE_DO_MODELO)  # stash reescreve

    assert [(a.tamanho_bytes, a.motivo) for a in _parados(home)] == [
        (0, "parado há 100 dias; 1 stash")
    ]


def test_arquivos_modificados_e_nao_rastreados_sao_trabalho_nao_salvo(home: Path) -> None:
    repo = home / "dev" / "app"
    _ = _escrever(repo / "README.md", b"editado\n", dias_atras=IDADE_DO_MODELO)
    _ = _escrever(repo / "notas.txt", b"novo\n", dias_atras=IDADE_DO_MODELO)

    assert [a.motivo for a in _parados(home)] == [
        "parado há 100 dias; 2 arquivos modificados ou não rastreados"
    ]


@pytest.mark.parametrize(
    ("build", "manifesto"),
    [
        (".venv", None),
        ("venv", None),
        ("target", "Cargo.toml"),
        (".build", "Package.swift"),
        ("pacotes/web/node_modules", None),
    ],
    ids=[".venv", "venv", "target-do-rust", ".build-do-swift", "node_modules-aninhado"],
)
def test_build_pesado_reconhecido_entra_no_tamanho(
    home: Path, build: str, manifesto: str | None
) -> None:
    repo = home / "dev" / "app"
    pasta_build = repo / build
    if manifesto is not None:
        _commitar(repo, manifesto, dias_atras=IDADE_DO_MODELO)
        _ = _git(repo, "push", "--quiet")
    _ = _escrever(pasta_build / "fundo" / "blob.bin", b"x" * 700)

    assert [a.tamanho_bytes for a in _parados(home)] == [700]


@pytest.mark.parametrize("build", ["target", ".build"])
def test_pasta_de_build_sem_o_manifesto_ao_lado_nao_conta(home: Path, build: str) -> None:
    _ = _escrever(home / "dev" / "app" / build / "blob.bin", b"x" * 700)

    assert _parados(home) == []


def _bytes_de_tudo(raiz: Path) -> int:
    return sum(p.lstat().st_size for p in raiz.rglob("*") if not p.is_dir() or p.is_symlink())


def test_repo_fora_de_dev_e_achado_com_o_tamanho_do_repo_inteiro(home: Path) -> None:
    (home / "Documents").mkdir()
    repo = (home / "dev" / "app").rename(home / "Documents" / "app")
    _ = _escrever(repo / "node_modules" / "index.js", b"x" * 300)

    achados = coletar_projetos(home, home / "dev", HOJE)

    fora = _da_categoria(achados, Categoria.GIT_FORA_DE_DEV)
    assert [(a.caminho, a.tamanho_bytes, a.motivo) for a in fora] == [
        (repo, _bytes_de_tudo(repo), "repositório git fora de ~/dev")
    ]


def test_repo_dentro_de_dev_nao_e_achado_de_fora_de_dev(home: Path) -> None:
    achados = coletar_projetos(home, home / "dev", HOJE)

    assert _da_categoria(achados, Categoria.GIT_FORA_DE_DEV) == []


def _caminhos(home: Path) -> set[Path]:
    return {Path(a.caminho) for a in coletar_projetos(home, home / "dev", HOJE)}


@pytest.mark.parametrize(
    "escondido",
    [
        "Library/Application Support/app",
        ".Trash/app",
        "Documents/node_modules/app",
        "Documents/.venv/app",
        "Documents/venv/app",
        "dev/app/vendor/app",
    ],
    ids=["Library", "Trash", "node_modules", ".venv", "venv", "repo-dentro-de-repo"],
)
def test_descoberta_nao_desce_onde_nao_deve(home: Path, escondido: str) -> None:
    # Fora de dev, um repo achado viraria GIT_FORA_DE_DEV: não aparecer prova que não foi achado.
    destino = home / escondido
    _ = shutil.copytree(home / "dev" / "app", destino, symlinks=True)

    assert destino not in _caminhos(home)


def test_descoberta_nao_segue_symlink(home: Path, tmp_path: Path) -> None:
    fora_do_home = shutil.copytree(home / "dev" / "app", tmp_path / "fora", symlinks=True)
    (home / "atalho").symlink_to(fora_do_home)

    assert home / "atalho" not in _caminhos(home)


def _repo_com_build_fora_de_dev(home: Path, nome: str) -> Path:
    destino = shutil.copytree(home / "dev" / "app", home / "Documents" / nome, symlinks=True)
    _ = _escrever(destino / "node_modules" / "index.js", b"x" * 100)
    return destino


def test_repo_corrompido_e_pulado_com_log_e_o_resto_segue(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # HOME versionado (dotfiles): um git que procura o repo para cima leria o do HOME.
    _ = _git(home, "init", "--quiet")
    corrompido = home / "Documents" / "corrompido"
    (corrompido / ".git").mkdir(parents=True)
    saudavel = _repo_com_build_fora_de_dev(home, "saudavel")

    with caplog.at_level(logging.WARNING, logger="antilixo.coletores.projetos"):
        caminhos = _caminhos(home)

    assert corrompido not in caminhos
    assert saudavel in caminhos
    assert str(corrompido) in caplog.text


def test_git_ausente_pula_os_repos_com_log(home: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="antilixo.coletores.projetos"):
        achados = coletar_projetos(home, home / "dev", HOJE, git="/nao/existe/git")

    assert achados == ()
    assert str(home / "dev" / "app") in caplog.text


def test_pasta_sem_permissao_e_pulada_com_log_e_o_resto_segue(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    trancada = home / "Trancada"
    trancada.mkdir(mode=0o000)
    saudavel = _repo_com_build_fora_de_dev(home, "saudavel")

    with caplog.at_level(logging.WARNING, logger="antilixo.coletores.projetos"):
        caminhos = _caminhos(home)
    trancada.chmod(0o700)  # deixa o pytest limpar o tmp_path

    assert saudavel in caminhos
    assert str(trancada) in caplog.text


def test_arquivo_rastreado_apagado_e_trabalho_nao_salvo(home: Path) -> None:
    (home / "dev" / "app" / "README.md").unlink()

    assert [a.motivo for a in _parados(home)] == [
        "parado há 100 dias; 1 arquivo modificado ou não rastreado"
    ]


def _esparso(caminho: Path, tamanho: int) -> None:
    """Arquivo com `tamanho` bytes aparentes sem ocupar disco: o coletor mede st_size."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("wb") as arquivo:
        _ = arquivo.truncate(tamanho)


def test_motivo_diz_dias_build_por_tipo_e_trabalho_nao_salvo(home: Path) -> None:
    repo = home / "dev" / "app"
    _esparso(repo / ".venv" / "lib.so", 450_000_000)
    _esparso(repo / "node_modules" / "a.bin", 700_000_000)
    _esparso(repo / "pacotes" / "web" / "node_modules" / "b.bin", 500_000_000)
    for nome, dias in (("a.txt", 95), ("b.txt", 93), ("c.txt", 92)):
        _commitar(repo, nome, dias_atras=dias)

    assert [(a.tamanho_bytes, a.motivo) for a in _parados(home)] == [
        (
            1_650_000_000,
            "parado há 92 dias; 1,2 GB em node_modules; 450 MB em .venv; 3 commits sem push",
        )
    ]


@pytest.mark.parametrize(("dias", "parado"), [(60, False), (61, True)])
def test_parado_e_mais_de_60_dias(home: Path, dias: int, parado: bool) -> None:  # noqa: FBT001  # motivo: parâmetro do parametrize
    repo = home / "dev" / "app"
    _ = _escrever(repo / "node_modules" / "index.js", b"x" * 10)
    _ = _escrever(repo / "README.md", b"# projeto\n", dias_atras=dias)
    _ = _escrever(repo / ".gitignore", (repo / ".gitignore").read_bytes(), dias_atras=dias)
    # O commit do modelo tem 100 dias; a atividade mais recente passa a ser a dos arquivos.
    assert bool(_parados(home)) is parado
