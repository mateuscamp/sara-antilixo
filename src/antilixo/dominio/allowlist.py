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

    Os dois caminhos chegam já resolvidos (sem `..` nem symlink): resolver exige disco, e o
    domínio não faz E/S. Comparação por componente, não por prefixo de texto, para que
    `.npm/_cacache-falso` não passe por `.npm/_cacache`.

    >>> esta_na_allowlist(PurePath("/u/.cache/uv/x"), PurePath("/u"))
    True
    """
    return any(alvo_resolvido.is_relative_to(home_resolvido / c) for c in CACHES_RECRIAVEIS)
