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
def test_limpar_aceita_dentro_da_allowlist(tmp_path: Path, cache: PurePath) -> None:
    # Sem este caso, um limpar() que recusa tudo passaria na suíte (achado A1 da revisão).
    dentro = tmp_path / cache / "pacote"
    dentro.mkdir(parents=True)

    limpar(dentro, home=tmp_path)
