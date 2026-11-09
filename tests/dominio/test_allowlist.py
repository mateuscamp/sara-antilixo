"""Regras puras da allowlist (ADR-0001), sem disco."""

from pathlib import PurePath

import pytest

from antilixo.dominio.allowlist import esta_na_allowlist


@pytest.mark.parametrize(
    ("alvo", "home"),
    [
        (PurePath("/Users/u/.npm/_cacache/../../Documents"), PurePath("/Users/u")),
        (PurePath("u/.npm/_cacache/pacote"), PurePath("u")),
    ],
    ids=["com-ponto-ponto", "relativo"],
)
def test_allowlist_recusa_caminho_nao_resolvido(alvo: PurePath, home: PurePath) -> None:
    # Achado A3: o domínio não resolve (sem disco), então recusa o que não chegou resolvido.
    assert not esta_na_allowlist(alvo, home)
