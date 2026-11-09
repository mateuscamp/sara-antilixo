"""Tipos que atravessam as pastas do antilixo (ADR-0001). Contrato fixado em 2026-11-09.

Fluxo de uma execução semanal (`python -m antilixo`):
coletores/ → tuple[Achado] → dominio.classificacao.classificar(...) → Veredito
→ acoes.limpar() em cada Veredito.apagar → ResultadoDaLimpeza
→ relatorio/ grava o Markdown, notifica e persiste Veredito.novo_estado.

Mudar um campo aqui quebra várias pastas de uma vez: exige o sim do humano.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import PurePath


class Categoria(StrEnum):
    """Origens de lixo medidas na formatação de 2026-11-08."""

    ORFAO_LIBRARY = "orfao-library"  # dados de app desinstalado na ~/Library
    PROJETO_PARADO = "projeto-parado"  # >60 dias, com build pesado ou trabalho sem push
    GIT_FORA_DE_DEV = "git-fora-de-dev"  # repositório fora de ~/dev
    FOTOS_EM_NUVEM = "fotos-em-nuvem"  # .photoslibrary dentro de iCloud/Proton Drive
    CACHE = "cache"  # caches recriáveis da allowlist


@dataclass(frozen=True, slots=True)
class Achado:
    """Uma coisa encontrada por um coletor. `caminho` é absoluto."""

    categoria: Categoria
    caminho: PurePath
    tamanho_bytes: int
    motivo: str  # frase curta para o relatório, ex.: "3 commits sem push, parado há 92 dias"


@dataclass(frozen=True, slots=True)
class AvisoAnterior:
    """O último aviso notificado de uma categoria (regra dos 20%, AGENTS.md)."""

    categoria: Categoria
    total_bytes_no_aviso: int


@dataclass(frozen=True, slots=True)
class MedicaoDeDisco:
    """Uso do disco num dia, para o orçamento de >20 GB em 30 dias."""

    dia: date
    usado_bytes: int


@dataclass(frozen=True, slots=True)
class Estado:
    """O que persiste entre execuções, em ~/.local/state/sara-antilixo/."""

    avisos_anteriores: tuple[AvisoAnterior, ...] = ()
    ultima_limpeza: date | None = None
    medicoes: tuple[MedicaoDeDisco, ...] = ()


@dataclass(frozen=True, slots=True)
class AvisoDeCategoria:
    """Uma categoria cuja soma passou de 2 GB. Sempre entra no relatório."""

    categoria: Categoria
    total_bytes: int
    achados: tuple[Achado, ...]
    notificar: bool  # primeira vez, ou cresceu >=20% desde o último aviso notificado


@dataclass(frozen=True, slots=True)
class Veredito:
    """Saída pura da classificação."""

    apagar: tuple[Achado, ...]  # só categoria CACHE, e só se a última limpeza tem >1 mês
    avisos: tuple[AvisoDeCategoria, ...]
    crescimento_do_disco_bytes: int | None  # preenchido só quando passa de 20 GB em 30 dias
    novo_estado: Estado


@dataclass(frozen=True, slots=True)
class FalhaDeLimpeza:
    """Um item da allowlist que não pôde ser apagado (ex.: PermissionError no meio do rmtree)."""

    achado: Achado
    erro: str


@dataclass(frozen=True, slots=True)
class ResultadoDaLimpeza:
    apagados: tuple[Achado, ...] = ()
    falhas: tuple[FalhaDeLimpeza, ...] = ()
