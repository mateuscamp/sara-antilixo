"""Allowlist de caches recriáveis que o antilixo pode apagar sozinho (ADR-0001).

Item novo exige ADR. Caminhos relativos ao HOME.
"""

from pathlib import PurePath

CACHES_RECRIAVEIS: tuple[PurePath, ...] = (
    PurePath(".npm/_cacache"),
    PurePath(".cache/uv"),
    PurePath("Library/Caches/Homebrew"),
    PurePath(".gradle/caches"),
)


def esta_na_allowlist(alvo_resolvido: PurePath, home_resolvido: PurePath) -> bool:
    """Diz se `alvo_resolvido` fica dentro (ou é a raiz) de um cache da allowlist.

    Os dois caminhos devem chegar já resolvidos (sem `..` nem symlink): resolver exige disco, e o
    domínio não faz E/S. O que dá para ver sem disco (relativo ou com `..`) é recusado; symlink
    no meio do caminho não dá, e é o chamador quem resolve (achado A3 da revisão de 2026-11-08).
    Comparação por componente, não por prefixo de texto, para que `.npm/_cacache-falso` não
    passe por `.npm/_cacache`.

    >>> esta_na_allowlist(PurePath("/u/.cache/uv/x"), PurePath("/u"))
    True
    """
    if not _parece_resolvido(alvo_resolvido) or not _parece_resolvido(home_resolvido):
        return False
    return any(alvo_resolvido.is_relative_to(home_resolvido / c) for c in CACHES_RECRIAVEIS)


def _parece_resolvido(caminho: PurePath) -> bool:
    return caminho.is_absolute() and ".." not in caminho.parts
