"""Classificação pura (ADR-0001, regras do domínio no AGENTS.md), sem disco."""

from datetime import date
from pathlib import PurePath

from antilixo.dominio.classificacao import classificar
from antilixo.dominio.modelo import (
    Achado,
    AvisoAnterior,
    Categoria,
    Estado,
    MedicaoDeDisco,
    Veredito,
)

HOJE = date(2026, 11, 9)
GB = 10**9


def _achado(categoria: Categoria, nome: str, tamanho_bytes: int) -> Achado:
    return Achado(categoria, PurePath(f"/Users/u/{nome}"), tamanho_bytes, "motivo")


def _classificar(*achados: Achado, estado: Estado | None = None, disco: int = 0) -> Veredito:
    return classificar(achados, estado or Estado(), HOJE, disco)


def test_cache_e_apagado_quando_nunca_houve_limpeza() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)

    veredito = _classificar(cache)

    assert veredito.apagar == (cache,)


def test_cache_nao_e_apagado_quando_ultima_limpeza_tem_menos_de_30_dias() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)

    veredito = _classificar(cache, estado=Estado(ultima_limpeza=date(2026, 10, 11)))

    assert veredito.apagar == ()


def test_cache_e_apagado_quando_ultima_limpeza_tem_exatamente_30_dias() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)

    veredito = _classificar(cache, estado=Estado(ultima_limpeza=date(2026, 10, 10)))

    assert veredito.apagar == (cache,)


def test_so_achados_de_cache_sao_apagados() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)
    orfao = _achado(Categoria.ORFAO_LIBRARY, "Library/Application Support/com.x", 1 * GB)

    veredito = _classificar(cache, orfao)

    assert veredito.apagar == (cache,)


def test_limpeza_grava_hoje_como_ultima_limpeza() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)

    veredito = _classificar(cache, estado=Estado(ultima_limpeza=date(2026, 9, 1)))

    assert veredito.novo_estado.ultima_limpeza == HOJE


def test_sem_cache_para_apagar_ultima_limpeza_nao_muda() -> None:
    orfao = _achado(Categoria.ORFAO_LIBRARY, "Library/Application Support/com.x", 1 * GB)

    veredito = _classificar(orfao, estado=Estado(ultima_limpeza=date(2026, 9, 1)))

    assert veredito.novo_estado.ultima_limpeza == date(2026, 9, 1)


def test_categoria_cuja_soma_passa_de_2_gb_vira_aviso_com_total_e_achados() -> None:
    grande = _achado(Categoria.PROJETO_PARADO, "velho/node_modules", 1_500_000_000)
    pequeno = _achado(Categoria.PROJETO_PARADO, "antigo/.venv", 600_000_000)

    veredito = _classificar(grande, pequeno)

    assert [(a.categoria, a.total_bytes, a.achados) for a in veredito.avisos] == [
        (Categoria.PROJETO_PARADO, 2_100_000_000, (grande, pequeno))
    ]


def test_categoria_com_exatamente_2_gb_nao_vira_aviso() -> None:
    achado = _achado(Categoria.GIT_FORA_DE_DEV, "Desktop/repo", 2 * GB)

    veredito = _classificar(achado)

    assert veredito.avisos == ()


def test_caches_apagados_nesta_execucao_nao_contam_para_o_aviso() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 3 * GB)

    veredito = _classificar(cache)

    assert veredito.avisos == ()


def test_caches_que_esperam_a_proxima_limpeza_contam_para_o_aviso() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 3 * GB)

    veredito = _classificar(cache, estado=Estado(ultima_limpeza=date(2026, 11, 1)))

    assert [(a.categoria, a.total_bytes) for a in veredito.avisos] == [(Categoria.CACHE, 3 * GB)]


def test_categoria_sem_aviso_anterior_notifica() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 5 * GB)

    veredito = _classificar(achado)

    assert [a.notificar for a in veredito.avisos] == [True]


def test_categoria_ja_avisada_que_cresceu_menos_de_20_porcento_nao_notifica() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 5_999_999_999)
    anterior = AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 5 * GB)

    veredito = _classificar(achado, estado=Estado(avisos_anteriores=(anterior,)))

    assert [a.notificar for a in veredito.avisos] == [False]


def test_categoria_ja_avisada_que_cresceu_exatamente_20_porcento_notifica() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 6 * GB)
    anterior = AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 5 * GB)

    veredito = _classificar(achado, estado=Estado(avisos_anteriores=(anterior,)))

    assert [a.notificar for a in veredito.avisos] == [True]


def test_novo_estado_guarda_o_total_da_categoria_notificada() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 7 * GB)
    anterior = AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 5 * GB)

    veredito = _classificar(achado, estado=Estado(avisos_anteriores=(anterior,)))

    assert veredito.novo_estado.avisos_anteriores == (
        AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 7 * GB),
    )


def test_categoria_avisada_sem_notificar_mantem_o_total_do_ultimo_aviso() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 5_500_000_000)
    anterior = AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 5 * GB)

    veredito = _classificar(achado, estado=Estado(avisos_anteriores=(anterior,)))

    assert veredito.novo_estado.avisos_anteriores == (anterior,)


def test_categoria_que_caiu_abaixo_de_2_gb_sai_dos_avisos_anteriores() -> None:
    achado = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 1 * GB)
    anterior = AvisoAnterior(Categoria.FOTOS_EM_NUVEM, 5 * GB)

    veredito = _classificar(achado, estado=Estado(avisos_anteriores=(anterior,)))

    assert veredito.novo_estado.avisos_anteriores == ()


def test_medicao_de_hoje_e_acrescentada_ao_estado() -> None:
    antiga = MedicaoDeDisco(date(2026, 11, 2), 100 * GB)

    veredito = _classificar(estado=Estado(medicoes=(antiga,)), disco=110 * GB)

    assert veredito.novo_estado.medicoes == (antiga, MedicaoDeDisco(HOJE, 110 * GB))


def test_medicoes_com_mais_de_60_dias_saem_do_estado() -> None:
    velha = MedicaoDeDisco(date(2026, 9, 9), 90 * GB)  # 61 dias
    limite = MedicaoDeDisco(date(2026, 9, 10), 95 * GB)  # 60 dias

    veredito = _classificar(estado=Estado(medicoes=(velha, limite)), disco=100 * GB)

    assert veredito.novo_estado.medicoes == (limite, MedicaoDeDisco(HOJE, 100 * GB))


def test_segunda_execucao_no_mesmo_dia_substitui_a_medicao_do_dia() -> None:
    manha = MedicaoDeDisco(HOJE, 100 * GB)

    veredito = _classificar(estado=Estado(medicoes=(manha,)), disco=101 * GB)

    assert veredito.novo_estado.medicoes == (MedicaoDeDisco(HOJE, 101 * GB),)


def test_medicoes_repetidas_de_dias_passados_ficam_com_a_ultima_da_entrada() -> None:
    primeira = MedicaoDeDisco(date(2026, 10, 10), 90 * GB)
    ultima = MedicaoDeDisco(primeira.dia, 105 * GB)
    outro_dia = MedicaoDeDisco(date(2026, 11, 2), 110 * GB)
    estado = Estado(medicoes=(outro_dia, primeira, outro_dia, ultima))

    veredito = _classificar(estado=estado, disco=120 * GB)

    assert veredito.novo_estado.medicoes == (ultima, outro_dia, MedicaoDeDisco(HOJE, 120 * GB))
    assert veredito.crescimento_do_disco_bytes is None


def test_crescimento_de_mais_de_20_gb_em_30_dias_e_informado() -> None:
    inicio = MedicaoDeDisco(date(2026, 10, 10), 100 * GB)  # 30 dias: dentro
    meio = MedicaoDeDisco(date(2026, 10, 20), 110 * GB)

    veredito = _classificar(estado=Estado(medicoes=(inicio, meio)), disco=120 * GB + 1)

    assert veredito.crescimento_do_disco_bytes == 20 * GB + 1


def test_crescimento_de_ate_20_gb_em_30_dias_nao_e_informado() -> None:
    inicio = MedicaoDeDisco(date(2026, 10, 10), 100 * GB)

    veredito = _classificar(estado=Estado(medicoes=(inicio,)), disco=120 * GB)

    assert veredito.crescimento_do_disco_bytes is None


def test_medicao_de_31_dias_atras_nao_entra_no_orcamento() -> None:
    fora = MedicaoDeDisco(date(2026, 10, 9), 50 * GB)  # 31 dias
    dentro = MedicaoDeDisco(date(2026, 10, 10), 100 * GB)  # 30 dias

    veredito = _classificar(estado=Estado(medicoes=(fora, dentro)), disco=110 * GB)

    assert veredito.crescimento_do_disco_bytes is None


def test_so_a_medicao_de_hoje_da_crescimento_zero() -> None:
    veredito = _classificar(disco=500 * GB)

    assert veredito.crescimento_do_disco_bytes is None


def test_achados_do_aviso_vem_em_tamanho_decrescente_com_desempate_por_caminho() -> None:
    pequeno = _achado(Categoria.PROJETO_PARADO, "a/.venv", 1 * GB)
    empate_b = _achado(Categoria.PROJETO_PARADO, "b/node_modules", 2 * GB)
    empate_a = _achado(Categoria.PROJETO_PARADO, "a/node_modules", 2 * GB)

    veredito = _classificar(pequeno, empate_b, empate_a)

    assert [a.achados for a in veredito.avisos] == [(empate_a, empate_b, pequeno)]


def test_apagar_vem_em_tamanho_decrescente_com_desempate_por_caminho() -> None:
    pequeno = _achado(Categoria.CACHE, ".cache/uv", 1 * GB)
    empate_b = _achado(Categoria.CACHE, ".npm/_cacache", 2 * GB)
    empate_a = _achado(Categoria.CACHE, ".gradle/caches", 2 * GB)

    veredito = _classificar(pequeno, empate_b, empate_a)

    assert veredito.apagar == (empate_a, empate_b, pequeno)


def test_avisos_seguem_a_ordem_de_declaracao_das_categorias() -> None:
    fotos = _achado(Categoria.FOTOS_EM_NUVEM, "iCloud/Fotos.photoslibrary", 3 * GB)
    orfao = _achado(Categoria.ORFAO_LIBRARY, "Library/Application Support/com.x", 3 * GB)
    git = _achado(Categoria.GIT_FORA_DE_DEV, "Desktop/repo", 3 * GB)

    veredito = _classificar(fotos, orfao, git)

    assert [a.categoria for a in veredito.avisos] == [
        Categoria.ORFAO_LIBRARY,
        Categoria.GIT_FORA_DE_DEV,
        Categoria.FOTOS_EM_NUVEM,
    ]


def test_medicao_com_data_futura_sai_do_estado() -> None:
    futura = MedicaoDeDisco(date(2026, 12, 1), 50 * GB)

    veredito = _classificar(estado=Estado(medicoes=(futura,)), disco=100 * GB)

    assert veredito.novo_estado.medicoes == (MedicaoDeDisco(HOJE, 100 * GB),)


def test_crescimento_compara_o_uso_de_hoje_mesmo_com_medicao_futura_no_estado() -> None:
    inicio = MedicaoDeDisco(date(2026, 10, 15), 100 * GB)
    futura = MedicaoDeDisco(date(2026, 12, 1), 50 * GB)

    veredito = _classificar(estado=Estado(medicoes=(inicio, futura)), disco=130 * GB)

    assert veredito.crescimento_do_disco_bytes == 30 * GB


def test_ultima_limpeza_depois_de_hoje_permite_limpar() -> None:
    cache = _achado(Categoria.CACHE, ".npm/_cacache", 1 * GB)

    veredito = _classificar(cache, estado=Estado(ultima_limpeza=date(2027, 6, 1)))

    assert veredito.apagar == (cache,)


def test_medicoes_do_estado_ficam_ordenadas_por_dia() -> None:
    depois = MedicaoDeDisco(date(2026, 11, 2), 105 * GB)
    antes = MedicaoDeDisco(date(2026, 10, 20), 100 * GB)

    veredito = _classificar(estado=Estado(medicoes=(depois, antes)), disco=110 * GB)

    assert veredito.novo_estado.medicoes == (antes, depois, MedicaoDeDisco(HOJE, 110 * GB))
