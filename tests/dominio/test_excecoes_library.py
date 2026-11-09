"""Exceções da regra de órfãos da ~/Library, por pasta (regras de 2026-11-09)."""

import pytest

from antilixo.dominio.excecoes_library import e_excecao


def test_excecao_de_nome_solto_vale_so_na_pasta_dela() -> None:
    assert e_excecao("Databases", "WebKit")
    assert not e_excecao("Databases", "Application Support")


@pytest.mark.parametrize("pasta", ["Caches", "Application Support", "Logs"])
def test_excecao_com_forma_de_bundle_id_vale_em_toda_pasta(pasta: str) -> None:
    assert e_excecao("com.crashlytics.data", pasta)


def test_excecao_ignora_maiusculas_no_nome() -> None:
    assert e_excecao("HOMEBREW", "Caches")


def test_nome_fora_da_lista_nao_e_excecao() -> None:
    assert not e_excecao("Notion", "Application Support")
