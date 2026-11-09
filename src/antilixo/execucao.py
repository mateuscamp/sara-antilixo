"""Uma execução semanal do antilixo: coleta, classifica, limpa, relata (ADR-0001)."""

import dataclasses
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from antilixo.acoes.limpar import ForaDaAllowlistError, limpar
from antilixo.coletores.caches import coletar_caches
from antilixo.coletores.disco import medir_uso_do_disco
from antilixo.coletores.fotos import coletar_fotos_em_nuvem
from antilixo.coletores.library import coletar_orfaos_library
from antilixo.coletores.projetos import coletar_projetos
from antilixo.dominio.classificacao import classificar
from antilixo.dominio.modelo import (
    Achado,
    Estado,
    FalhaDeLimpeza,
    ResultadoDaLimpeza,
    Veredito,
)
from antilixo.relatorio.estado_em_disco import gravar_estado, ler_estado
from antilixo.relatorio.markdown import gravar_relatorio, montar_relatorio
from antilixo.relatorio.notificacao import ExecutorDeComando, notificar

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Ambiente:
    """O que vem de fora: HOME, relógio, onde estão os apps e quem roda o osascript."""

    home: Path
    agora: datetime
    pastas_de_apps: tuple[Path, ...]
    executor: ExecutorDeComando
    # Nome e função de cada coletor; None = os quatro reais. Testes trocam por coletores falsos.
    coletores: tuple[tuple[str, Coletor], ...] | None = None


type Coletor = Callable[[Ambiente], tuple[Achado, ...]]


@dataclass(frozen=True, slots=True)
class Coleta:
    achados: tuple[Achado, ...]
    falhas: tuple[str, ...]  # "nome: erro" de cada coletor que quebrou


def executar(ambiente: Ambiente) -> None:
    """Roda uma vez: coleta, classifica, apaga o que a allowlist permite, grava e notifica."""
    pasta_de_estado = ambiente.home / ".local" / "state" / "sara-antilixo"
    hoje = ambiente.agora.date()
    estado = ler_estado(pasta_de_estado, hoje=hoje)
    coleta = coletar_tudo(ambiente)
    veredito = classificar(coleta.achados, estado, hoje, medir_uso_do_disco(ambiente.home))
    resultado = _limpar_todos(veredito.apagar, ambiente.home)
    # Estado antes do relatório: se o relatório não gravar, a data da limpeza não se perde e a
    # semana seguinte não apaga de novo (revisão de 2026-11-09).
    gravar_estado(pasta_de_estado, _estado_a_gravar(estado, veredito, resultado))
    texto = montar_relatorio(veredito, resultado, ambiente.agora, coleta.falhas)
    try:
        _ = gravar_relatorio(texto, pasta_de_estado, ambiente.agora)
    except OSError as erro:
        logger.warning("relatório não gravado em %s: %s", pasta_de_estado, erro)
    _ = notificar(veredito, resultado, ambiente.executor)


def coletar_tudo(ambiente: Ambiente) -> Coleta:
    """Roda cada coletor; um que quebra vira linha no relatório e os outros seguem."""
    achados: list[Achado] = []
    falhas: list[str] = []
    for nome, coletor in ambiente.coletores or _COLETORES_REAIS:
        try:
            achados.extend(coletor(ambiente))
        # Fronteira da execução semanal: um coletor quebrado não pode calar os outros. O erro vai
        # para o relatório e, com o traceback, para o log.
        except Exception as erro:
            logger.exception("coletor %s falhou", nome)
            falhas.append(f"{nome}: {type(erro).__name__}: {erro}")
    return Coleta(tuple(achados), tuple(falhas))


_COLETORES_REAIS: tuple[tuple[str, Coletor], ...] = (
    ("caches", lambda a: coletar_caches(a.home)),
    ("fotos-em-nuvem", lambda a: coletar_fotos_em_nuvem(a.home)),
    ("orfaos-library", lambda a: coletar_orfaos_library(a.home, a.pastas_de_apps)),
    ("projetos", lambda a: coletar_projetos(a.home, a.home / "dev", a.agora.date())),
)


def _limpar_todos(apagar: tuple[Achado, ...], home: Path) -> ResultadoDaLimpeza:
    apagados: list[Achado] = []
    falhas: list[FalhaDeLimpeza] = []
    for achado in apagar:
        try:
            limpar(Path(achado.caminho), home=home)
        except (OSError, ForaDaAllowlistError) as erro:
            # Um item que falha (ex.: PermissionError no meio do rmtree, achado 3 de
            # 2026-11-09) vira linha no relatório; os demais seguem.
            logger.warning("limpeza falhou: %s (%s)", achado.caminho, erro)
            falhas.append(FalhaDeLimpeza(achado, str(erro)))
            continue
        apagados.append(achado)
    return ResultadoDaLimpeza(apagados=tuple(apagados), falhas=tuple(falhas))


def _estado_a_gravar(anterior: Estado, veredito: Veredito, resultado: ResultadoDaLimpeza) -> Estado:
    # Se a limpeza falhou em tudo, a data não avança: tenta de novo na semana seguinte, em vez
    # de esperar um mês sem ter limpado nada (decidido em 2026-11-09).
    if veredito.apagar and not resultado.apagados:
        return dataclasses.replace(veredito.novo_estado, ultima_limpeza=anterior.ultima_limpeza)
    return veredito.novo_estado
