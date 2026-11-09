"""Coletor de caches recriáveis da allowlist (ADR-0001)."""

from pathlib import Path

from antilixo.coletores.disco import somar_tamanho
from antilixo.dominio.allowlist import CACHES_RECRIAVEIS, esta_na_allowlist
from antilixo.dominio.modelo import Achado, Categoria


def coletar_caches(home: Path) -> tuple[Achado, ...]:
    """Um `Achado` por cache da allowlist que existe sob `home`.

    Cache que, resolvido, sai da allowlist (ele ou um ancestral é symlink para fora) não vira
    achado: `limpar()` o recusaria, e o relatório mostraria um aviso que nenhuma ação resolve.
    """
    home_resolvido = home.resolve()
    return tuple(
        Achado(
            Categoria.CACHE,
            home / cache,
            somar_tamanho(home / cache),
            f"cache recriável da allowlist: ~/{cache.as_posix()}",
        )
        for cache in CACHES_RECRIAVEIS
        if (home / cache).is_dir() and esta_na_allowlist((home / cache).resolve(), home_resolvido)
    )
