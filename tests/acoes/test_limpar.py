"""Fitness function do ADR-0001: nada é apagado fora da allowlist."""

from pathlib import Path, PurePath

import pytest

from antilixo.acoes.limpar import ForaDaAllowlistError, limpar
from antilixo.dominio.allowlist import CACHES_RECRIAVEIS


def _montar_home(home: Path) -> Path:
    """HOME falso com um cache da allowlist e um arquivo do usuário. Devolve o arquivo."""
    (home / ".npm" / "_cacache").mkdir(parents=True)
    (home / ".npm" / "_cacache-falso").mkdir()
    documentos = home / "Documents"
    documentos.mkdir()
    importante = documentos / "importante.txt"
    _ = importante.write_text("não apague")
    (home / ".npm" / "_cacache" / "atalho").symlink_to(documentos)
    return importante


@pytest.mark.parametrize(
    "alvo_relativo",
    [
        "Documents/importante.txt",
        ".npm/_cacache/../../Documents/importante.txt",
        ".npm/_cacache/atalho/importante.txt",
        ".npm/_cacache-falso",
    ],
    ids=["fora", "fuga-por-ponto-ponto", "symlink-para-fora", "prefixo-parecido"],
)
def test_limpar_recusa_fora_da_allowlist(tmp_path: Path, alvo_relativo: str) -> None:
    importante = _montar_home(tmp_path)
    alvo = tmp_path / alvo_relativo

    with pytest.raises(ForaDaAllowlistError):
        limpar(alvo, home=tmp_path)

    assert importante.read_text() == "não apague"
    assert (tmp_path / ".npm" / "_cacache-falso").is_dir()


@pytest.mark.parametrize("cache", CACHES_RECRIAVEIS, ids=[c.as_posix() for c in CACHES_RECRIAVEIS])
def test_limpar_apaga_dentro_da_allowlist(tmp_path: Path, cache: PurePath) -> None:
    # Também cobre o achado A1 da revisão: um limpar() que recusa tudo reprova aqui.
    pasta = tmp_path / cache / "pacote"
    pasta.mkdir(parents=True)
    _ = (pasta / "blob").write_bytes(b"x")
    arquivo = tmp_path / cache / "solto.bin"
    _ = arquivo.write_bytes(b"x")

    limpar(pasta, home=tmp_path)
    limpar(arquivo, home=tmp_path)

    assert not pasta.exists()
    assert not arquivo.exists()
    assert (tmp_path / cache).is_dir()


def test_limpar_por_atalho_apaga_o_destino_e_o_atalho(tmp_path: Path) -> None:
    # Achado A2: apaga o caminho que passou na checagem (o resolvido), não o texto recebido.
    # Achado 6 (revisão de 2026-11-09): o atalho dentro do cache não fica pendurado.
    cache = tmp_path / ".cache" / "uv"
    destino = cache / "real"
    destino.mkdir(parents=True)
    atalho = cache / "atalho"
    atalho.symlink_to(destino)

    limpar(atalho, home=tmp_path)

    assert not destino.exists()
    assert not atalho.is_symlink()


def test_limpar_nao_apaga_atalho_fora_da_allowlist(tmp_path: Path) -> None:
    # O destino está no cache e pode ir; o atalho mora em Documents e fica (zero deleção fora).
    destino = tmp_path / ".cache" / "uv" / "real"
    destino.mkdir(parents=True)
    documentos = tmp_path / "Documents"
    documentos.mkdir()
    atalho = documentos / "atalho"
    atalho.symlink_to(destino)

    limpar(atalho, home=tmp_path)

    assert not destino.exists()
    assert atalho.is_symlink()


def test_limpar_alvo_que_ja_sumiu_nao_e_erro(tmp_path: Path) -> None:
    # Achado 2 (revisão de 2026-11-09): a ferramenta dona do cache pode ter apagado antes.
    (tmp_path / ".npm" / "_cacache").mkdir(parents=True)

    limpar(tmp_path / ".npm" / "_cacache" / "sumiu", home=tmp_path)
