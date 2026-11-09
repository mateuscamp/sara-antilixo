"""Exceções da regra de órfãos da ~/Library, por pasta (regras de 2026-11-09)."""

import pytest

from antilixo.dominio.excecoes_library import EXCECOES_LIBRARY, e_excecao


def test_excecoes_nao_repetem_nome_sem_diferenciar_maiusculas() -> None:
    nomes = [excecao.nome.casefold() for excecao in EXCECOES_LIBRARY]

    assert len(nomes) == len(set(nomes))


def test_excecoes_so_referenciam_as_sete_pastas_coletadas_da_library() -> None:
    permitidas = {
        "Application Support",
        "Caches",
        "Containers",
        "Saved Application State",
        "HTTPStorages",
        "WebKit",
        "Logs",
    }

    assert all(excecao.pastas <= permitidas for excecao in EXCECOES_LIBRARY)


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
