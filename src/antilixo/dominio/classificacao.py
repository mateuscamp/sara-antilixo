"""Classificação apagar/avisar do antilixo (ADR-0001, regras do domínio no AGENTS.md). Pura."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta

from antilixo.dominio.modelo import (
    Achado,
    AvisoAnterior,
    AvisoDeCategoria,
    Categoria,
    Estado,
    MedicaoDeDisco,
    Veredito,
)

# AGENTS.md: limpeza automática no máximo uma vez por mês.
INTERVALO_MINIMO_ENTRE_LIMPEZAS = timedelta(days=30)
# AGENTS.md: aviso quando a soma de uma categoria passa de 2 GB (decimal, a unidade do Finder).
LIMIAR_DE_AVISO_BYTES = 2 * 10**9
# ADR-0001, orçamento de disco: o estado guarda 60 dias de medições.
JANELA_DE_MEDICOES = timedelta(days=60)
JANELA_DO_ORCAMENTO = timedelta(days=30)
LIMIAR_DO_ORCAMENTO_BYTES = 20 * 10**9  # ADR-0001: disco cresce >20 GB em 30 dias


def classificar(
    achados: tuple[Achado, ...], estado: Estado, hoje: date, uso_do_disco_bytes: int
) -> Veredito:
    pode_limpar = (
        estado.ultima_limpeza is None
        or hoje - estado.ultima_limpeza >= INTERVALO_MINIMO_ENTRE_LIMPEZAS
    )
    apagar = _em_ordem(a for a in achados if pode_limpar and a.categoria is Categoria.CACHE)
    avisos = _avisos(tuple(a for a in achados if a not in apagar), estado)
    novo_estado = replace(
        estado,
        ultima_limpeza=hoje if apagar else estado.ultima_limpeza,
        avisos_anteriores=_avisos_anteriores(avisos, estado),
        medicoes=_medicoes(estado.medicoes, hoje, uso_do_disco_bytes),
    )
    return Veredito(
        apagar=apagar,
        avisos=avisos,
        crescimento_do_disco_bytes=_crescimento_do_disco(novo_estado.medicoes, hoje),
        novo_estado=novo_estado,
    )


def _avisos(achados: tuple[Achado, ...], estado: Estado) -> tuple[AvisoDeCategoria, ...]:
    anteriores = {a.categoria: a.total_bytes_no_aviso for a in estado.avisos_anteriores}
    avisos: list[AvisoDeCategoria] = []
    for categoria in Categoria:
        da_categoria = _em_ordem(a for a in achados if a.categoria is categoria)
        total = sum(a.tamanho_bytes for a in da_categoria)
        if total > LIMIAR_DE_AVISO_BYTES:
            anterior = anteriores.get(categoria)
            notificar = anterior is None or _cresceu_o_bastante(total, anterior)
            avisos.append(AvisoDeCategoria(categoria, total, da_categoria, notificar=notificar))
    return tuple(avisos)


def _cresceu_o_bastante(total: int, anterior: int) -> bool:
    # AGENTS.md: achado já avisado só volta a notificar se crescer >=20%. Em inteiros (6/5),
    # para que o limite exato não dependa de arredondamento de float.
    return total * 5 >= anterior * 6


def _avisos_anteriores(
    avisos: tuple[AvisoDeCategoria, ...], estado: Estado
) -> tuple[AvisoAnterior, ...]:
    """Notificada agora guarda o total atual; avisada sem notificar mantém o do último aviso.

    Categoria fora de `avisos` (caiu abaixo de 2 GB) some, para notificar de novo se voltar.
    """
    anteriores = {a.categoria: a for a in estado.avisos_anteriores}
    return tuple(
        AvisoAnterior(a.categoria, a.total_bytes) if a.notificar else anteriores[a.categoria]
        for a in avisos
    )


def _medicoes(
    medicoes: tuple[MedicaoDeDisco, ...], hoje: date, uso_do_disco_bytes: int
) -> tuple[MedicaoDeDisco, ...]:
    # A medição nova substitui a do mesmo dia (duas execuções num dia, decidido em 2026-11-09).
    recentes = tuple(m for m in medicoes if hoje - JANELA_DE_MEDICOES <= m.dia and m.dia != hoje)
    return (*recentes, MedicaoDeDisco(hoje, uso_do_disco_bytes))


def _crescimento_do_disco(medicoes: tuple[MedicaoDeDisco, ...], hoje: date) -> int | None:
    """Crescimento desde a medição mais antiga dos últimos 30 dias (limite incluído).

    `medicoes` já traz a de hoje, então a janela nunca fica vazia; sem outra, o crescimento é 0.
    """
    na_janela = [m for m in medicoes if m.dia >= hoje - JANELA_DO_ORCAMENTO]
    mais_antiga = min(na_janela, key=lambda m: m.dia)
    atual = max(na_janela, key=lambda m: m.dia)
    crescimento = atual.usado_bytes - mais_antiga.usado_bytes
    return crescimento if crescimento > LIMIAR_DO_ORCAMENTO_BYTES else None


def _em_ordem(achados: Iterable[Achado]) -> tuple[Achado, ...]:
    """Tamanho decrescente, desempate por caminho: o relatório não muda de ordem à toa."""
    return tuple(sorted(achados, key=lambda a: (-a.tamanho_bytes, a.caminho)))
