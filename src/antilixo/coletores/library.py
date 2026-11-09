"""Coletor de dados de apps desinstalados na ~/Library (AGENTS.md, regras de 2026-11-09).

Origem: 4,4 GB de dados de apps desinstalados na ~/Library na formatação de 2026-11-08.
"""

import logging
import plistlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from antilixo.coletores.disco import somar_tamanho
from antilixo.dominio.excecoes_library import EXCECOES_LIBRARY
from antilixo.dominio.modelo import Achado, Categoria

_log = logging.getLogger(__name__)

# Onde apps desinstalados deixam dados com o nome do bundle id (medido em 2026-11-08).
_PASTAS_DA_LIBRARY = (
    "Application Support",
    "Caches",
    "Containers",
    "Saved Application State",
    "HTTPStorages",
    "WebKit",
    "Logs",
)


def coletar_orfaos_library(home: Path, pastas_de_apps: tuple[Path, ...]) -> tuple[Achado, ...]:
    """Pastas da ~/Library sem app instalado correspondente.

    Nome com forma de bundle id casa com o bundle id do app (ou o prefixo dele com ponto); os
    outros nomes (Notion, Comet) casam com o nome do app. Regras de 2026-11-09, aprovadas pela
    sessão-mãe: falso positivo é aceitável, porque vira só aviso e nunca apaga.
    """
    instalados = _apps_instalados(pastas_de_apps)
    return tuple(
        Achado(
            Categoria.ORFAO_LIBRARY,
            pasta,
            somar_tamanho(pasta),
            f"{pasta.name} sem app instalado ({subpasta})",
        )
        for subpasta in _PASTAS_DA_LIBRARY
        for pasta in _subpastas(home / "Library" / subpasta)
        if not _e_do_sistema(pasta.name) and not _e_de_app_instalado(pasta.name, instalados)
    )


# Reverse-DNS: dois ou mais rótulos com ponto, o primeiro só letras (o domínio de topo). Proposta
# enviada à sessão-mãe em 2026-11-09; "node.js" passa por esta forma (falso positivo aceito).
_FORMA_DE_BUNDLE_ID = re.compile(r"[A-Za-z]+(\.[A-Za-z0-9_-]+)+")


def _tem_forma_de_bundle_id(nome: str) -> bool:
    return _FORMA_DE_BUNDLE_ID.fullmatch(nome) is not None


_EXCECOES = frozenset(e.casefold() for e in EXCECOES_LIBRARY)


def _e_do_sistema(nome: str) -> bool:
    chave = nome.casefold()
    return chave.startswith("com.apple.") or chave in _EXCECOES


@dataclass(frozen=True, slots=True)
class _Instalados:
    """O que identifica os apps instalados, já em casefold."""

    bundle_ids: frozenset[str]
    nomes: frozenset[str]  # nome do .app sem extensão, CFBundleName e CFBundleDisplayName


def _e_de_app_instalado(nome: str, instalados: _Instalados) -> bool:
    chave = nome.casefold()
    if not _tem_forma_de_bundle_id(nome):
        return chave in instalados.nomes
    return _e_de_bundle_id_instalado(chave, instalados.bundle_ids)


def _e_de_bundle_id_instalado(chave: str, instalados: frozenset[str]) -> bool:
    """O nome é o bundle id de um app instalado, ou começa por ele seguido de ponto.

    O ponto separa `com.microsoft.VSCode.ShipIt` (do VSCode) de `com.microsoft.VSCodeInsiders`
    (outro app). Sem diferenciar maiúsculas, como o APFS padrão e o próprio bundle id.
    Aprovado pela sessão-mãe em 2026-11-09.
    """
    return any(chave == i or chave.startswith(f"{i}.") for i in instalados)


def _subpastas(raiz: Path) -> list[Path]:
    """Pastas diretamente sob `raiz`, sem seguir symlinks; raiz ausente dá lista vazia."""
    if not raiz.is_dir():
        return []
    return sorted(p for p in raiz.iterdir() if p.is_dir() and not p.is_symlink())


def _apps_instalados(pastas_de_apps: tuple[Path, ...]) -> _Instalados:
    bundle_ids: set[str] = set()
    nomes: set[str] = set()
    for bundle in (b for pasta in pastas_de_apps for b in _bundles_sob(pasta)):
        nomes.add(bundle.stem.casefold())
        info = _ler_info_plist(bundle)
        bundle_ids.update(i.casefold() for i in _bundle_id(info))
        nomes.update(n.casefold() for n in _nomes_declarados(info))
    return _Instalados(frozenset(bundle_ids), frozenset(nomes))


# Bundles dentro de um .app com bundle id próprio, que deixa dados na ~/Library (extensões e
# itens de login). Aprovado pela sessão-mãe em 2026-11-09.
_ANINHADOS = ("Contents/PlugIns/*.appex", "Contents/Library/LoginItems/*.app")


def _bundles_sob(pasta: Path) -> list[Path]:
    """Apps em `pasta` e nas subpastas comuns (Utilities, pasta do fornecedor), mais os aninhados.

    Não desce no resto do .app nem segue symlinks: o Xcode.app sozinho tem centenas de milhares
    de arquivos.
    """
    bundles: list[Path] = []
    for raiz, subpastas, _arquivos in pasta.walk():
        apps = [s for s in subpastas if s.endswith(".app")]
        for nome in apps:
            app = raiz / nome
            bundles.append(app)
            bundles.extend(b for padrao in _ANINHADOS for b in app.glob(padrao))
        subpastas[:] = [s for s in subpastas if not s.endswith(".app")]
    return bundles


def _bundle_id(info: object) -> list[str]:
    match info:
        case {"CFBundleIdentifier": str(bundle_id)}:
            return [bundle_id]
        case _:
            return []


def _nomes_declarados(info: object) -> list[str]:
    """`CFBundleName` e `CFBundleDisplayName`, os que existirem como texto."""
    nomes: list[str] = []
    match info:
        case {"CFBundleName": str(nome)}:
            nomes.append(nome)
        case _:
            pass
    match info:
        case {"CFBundleDisplayName": str(nome)}:
            nomes.append(nome)
        case _:
            pass
    return nomes


def _ler_info_plist(app: Path) -> object:
    """O Info.plist do app, ou None se faltar ou não for legível."""
    info_plist = app / "Contents" / "Info.plist"
    try:
        with info_plist.open("rb") as arquivo:
            return cast("object", plistlib.load(arquivo))  # motivo: plistlib dá Any; match confere
    except OSError, plistlib.InvalidFileException:
        _log.info("Info.plist ilegível, app ignorado: %s", info_plist)
        return None
