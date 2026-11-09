"""Coletor de bibliotecas do Fotos dentro de pastas sincronizadas com a nuvem (ADR-0001).

Origem: 5,8 GB de biblioteca do Fotos presa no iCloud Drive na formatação de 2026-11-08.
"""

from pathlib import Path

from antilixo.coletores.disco import somar_tamanho
from antilixo.dominio.modelo import Achado, Categoria

# iCloud Drive mora em Mobile Documents; Proton Drive, Dropbox e afins (File Provider), em
# CloudStorage.
_PASTAS_SINCRONIZADAS = ("Mobile Documents", "CloudStorage")
_SUFIXO = ".photoslibrary"


def coletar_fotos_em_nuvem(home: Path) -> tuple[Achado, ...]:
    """Todo `*.photoslibrary` dentro do iCloud Drive ou do CloudStorage, com o tamanho."""
    return tuple(
        Achado(
            Categoria.FOTOS_EM_NUVEM,
            biblioteca,
            somar_tamanho(biblioteca),
            f"biblioteca do Fotos dentro de pasta sincronizada: {nome}",
        )
        for nome in _PASTAS_SINCRONIZADAS
        for biblioteca in _bibliotecas_sob(home / "Library" / nome)
    )


def _bibliotecas_sob(raiz: Path) -> list[Path]:
    """Bibliotecas sob `raiz`, sem descer dentro delas nem seguir symlinks."""
    encontradas: list[Path] = []
    for pasta, subpastas, _arquivos in raiz.walk():
        bibliotecas = [s for s in subpastas if s.endswith(_SUFIXO)]
        encontradas.extend(pasta / b for b in bibliotecas)
        # Path.walk desce só no que ficar em `subpastas`: tirar a biblioteca poda a descida.
        subpastas[:] = [s for s in subpastas if not s.endswith(_SUFIXO)]
    return encontradas
