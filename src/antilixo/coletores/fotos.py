"""Coletor de bibliotecas do Fotos dentro de pastas sincronizadas com a nuvem (ADR-0001).

Origem: 5,8 GB de biblioteca do Fotos presa no iCloud Drive na formatação de 2026-11-08.
"""

import logging
from pathlib import Path

from antilixo.coletores.disco import somar_tamanho
from antilixo.coletores.nao_lidas import resumir_pastas_nao_lidas
from antilixo.dominio.modelo import Achado, Categoria, Leitura

# iCloud Drive mora em Mobile Documents; Proton Drive, Dropbox e afins (File Provider), em
# CloudStorage.
_PASTAS_SINCRONIZADAS = ("Mobile Documents", "CloudStorage")
_SUFIXO = ".photoslibrary"

logger = logging.getLogger(__name__)


def coletar_fotos_em_nuvem(home: Path) -> Leitura:
    """Todo `*.photoslibrary` dentro do iCloud Drive ou do CloudStorage, com o tamanho.

    Cada conta sincronizada (filha de Mobile Documents ou de CloudStorage) é varrida à parte, para
    o que não deu para ler sair resumido por conta, e não pasta a pasta.
    """
    achados: list[Achado] = []
    nao_lidas: list[str] = []
    for nome in _PASTAS_SINCRONIZADAS:
        for conta in _contas_sob(home / "Library" / nome):
            erros: list[OSError] = []
            achados.extend(
                Achado(
                    Categoria.FOTOS_EM_NUVEM,
                    biblioteca,
                    somar_tamanho(biblioteca),
                    f"biblioteca do Fotos dentro de pasta sincronizada: {nome}",
                )
                for biblioteca in _bibliotecas_sob(conta, erros)
            )
            nao_lidas.extend(resumir_pastas_nao_lidas(f"{nome}/{conta.name}", conta, erros))
    for linha in nao_lidas:
        logger.warning("não lido: %s", linha)
    return Leitura(tuple(achados), tuple(nao_lidas))


def _contas_sob(pasta: Path) -> list[Path]:
    """Filhas diretas (uma por conta sincronizada); pasta ausente é um Mac sem esse serviço."""
    try:
        return sorted(p for p in pasta.iterdir() if p.is_dir() and not p.is_symlink())
    except FileNotFoundError:
        return []
    except OSError as erro:
        logger.warning("não lido: %s: %s", pasta, erro)
        return []


def _bibliotecas_sob(raiz: Path, erros: list[OSError]) -> list[Path]:
    """Bibliotecas sob `raiz`, sem descer dentro delas nem seguir symlinks."""
    encontradas: list[Path] = []
    for pasta, subpastas, _arquivos in raiz.walk(on_error=erros.append):
        bibliotecas = [s for s in subpastas if s.endswith(_SUFIXO)]
        encontradas.extend(pasta / b for b in bibliotecas)
        # Path.walk desce só no que ficar em `subpastas`: tirar a biblioteca poda a descida.
        subpastas[:] = [s for s in subpastas if not s.endswith(_SUFIXO)]
    return encontradas
