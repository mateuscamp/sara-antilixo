"""Uma execução semanal do antilixo: coleta, classifica, limpa, relata (ADR-0001)."""

import dataclasses
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from antilixo.acoes.limpar import ForaDaAllowlistError, limpar
from antilixo.coletores.caches import coletar_caches
from antilixo.coletores.disco import medir_uso_do_disco
from antilixo.coletores.fotos import coletar_fotos_em_nuvem
from antilixo.coletores.library import coletar_orfaos_library
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


def executar(ambiente: Ambiente) -> None:
    """Roda uma vez: coleta, classifica, apaga o que a allowlist permite, grava e notifica."""
    pasta_de_estado = ambiente.home / ".local" / "state" / "sara-antilixo"
    hoje = ambiente.agora.date()
    estado = ler_estado(pasta_de_estado, hoje=hoje)
    veredito = classificar(_coletar(ambiente), estado, hoje, medir_uso_do_disco(ambiente.home))
    resultado = _limpar_todos(veredito.apagar, ambiente.home)
    texto = montar_relatorio(veredito, resultado, ambiente.agora)
    _ = gravar_relatorio(texto, pasta_de_estado, ambiente.agora)
    gravar_estado(pasta_de_estado, _estado_a_gravar(estado, veredito, resultado))
    _ = notificar(veredito, resultado, ambiente.executor)


def _coletar(ambiente: Ambiente) -> tuple[Achado, ...]:
    home = ambiente.home
    return (
        *coletar_caches(home),
        *coletar_fotos_em_nuvem(home),
        *coletar_orfaos_library(home, ambiente.pastas_de_apps),
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
