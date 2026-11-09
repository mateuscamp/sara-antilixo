import sys
from collections.abc import Sequence
from pathlib import Path, PurePath

import pytest

from antilixo.dominio.modelo import (
    Achado,
    AvisoDeCategoria,
    Categoria,
    Estado,
    FalhaDeLimpeza,
    ResultadoDaLimpeza,
    Veredito,
)
from antilixo.relatorio.notificacao import ExecutorDeSubprocesso, notificar


class ExecutorFalso:
    """Guarda os comandos em vez de rodá-los: nenhuma notificação real sai do teste."""

    def __init__(self, *, sucesso: bool = True) -> None:
        self.chamadas: list[tuple[str, ...]] = []
        self._sucesso: bool = sucesso

    def executar(self, argumentos: Sequence[str]) -> bool:
        self.chamadas.append(tuple(argumentos))
        return self._sucesso


def _veredito(
    avisos: tuple[AvisoDeCategoria, ...] = (), crescimento: int | None = None
) -> Veredito:
    return Veredito(
        apagar=(), avisos=avisos, crescimento_do_disco_bytes=crescimento, novo_estado=Estado()
    )


def _aviso(categoria: Categoria, total: int, *, notificar: bool) -> AvisoDeCategoria:
    achado = Achado(categoria, PurePath("/Users/u/x"), total, "motivo")
    return AvisoDeCategoria(categoria, total, (achado,), notificar=notificar)


def test_sem_nada_novo_nao_chama_o_osascript() -> None:
    executor = ExecutorFalso()
    ja_avisado = _aviso(Categoria.PROJETO_PARADO, 3_000_000_000, notificar=False)

    disparou = notificar(_veredito((ja_avisado,)), ResultadoDaLimpeza(), executor)

    assert disparou is False
    assert executor.chamadas == []


def test_aviso_novo_vira_notificacao_curta_com_o_total_de_cada_categoria() -> None:
    executor = ExecutorFalso()
    avisos = (
        _aviso(Categoria.PROJETO_PARADO, 3_200_000_000, notificar=True),
        _aviso(Categoria.ORFAO_LIBRARY, 6_000_000_000, notificar=True),
        _aviso(Categoria.CACHE, 9_000_000_000, notificar=False),
    )

    disparou = notificar(_veredito(avisos), ResultadoDaLimpeza(), executor)

    texto = "3,2 GB em projetos parados; 6,0 GB de órfãos na Library"
    assert disparou is True
    assert executor.chamadas == [
        (
            "/usr/bin/osascript",
            "-e",
            f'display notification "{texto}" with title "antilixo"',
        )
    ]


def _texto_da_notificacao(executor: ExecutorFalso) -> str:
    assert len(executor.chamadas) == 1
    [(programa, opcao, script)] = executor.chamadas
    assert (programa, opcao) == ("/usr/bin/osascript", "-e")
    return script


def test_crescimento_do_disco_notifica_mesmo_sem_aviso() -> None:
    executor = ExecutorFalso()

    disparou = notificar(_veredito(crescimento=25_300_000_000), ResultadoDaLimpeza(), executor)

    assert disparou is True
    assert "disco cresceu 25,3 GB em 30 dias" in _texto_da_notificacao(executor)


def test_falha_de_limpeza_notifica_com_o_nome_do_item() -> None:
    executor = ExecutorFalso()
    cache = Achado(Categoria.CACHE, PurePath("/Users/u/.cache/uv"), 10, "cache")
    resultado = ResultadoDaLimpeza(falhas=(FalhaDeLimpeza(cache, "PermissionError"),))

    disparou = notificar(_veredito(), resultado, executor)

    assert disparou is True
    assert "falha ao limpar uv" in _texto_da_notificacao(executor)


def test_nome_da_falha_neutraliza_controle_bidirecional() -> None:
    executor = ExecutorFalso()
    cache = Achado(Categoria.CACHE, PurePath("/cache/uv\u202eoculto"), 10, "cache")
    resultado = ResultadoDaLimpeza(falhas=(FalhaDeLimpeza(cache, "PermissionError"),))

    _ = notificar(_veredito(), resultado, executor)

    texto = _desfazer_literal_applescript(_texto_da_notificacao(executor))
    assert texto == r"falha ao limpar uv\u202eoculto"


def test_varias_falhas_viram_uma_contagem() -> None:
    executor = ExecutorFalso()
    cache = Achado(Categoria.CACHE, PurePath("/Users/u/.cache/uv"), 10, "cache")
    falha = FalhaDeLimpeza(cache, "PermissionError")

    _ = notificar(_veredito(), ResultadoDaLimpeza(falhas=(falha, falha)), executor)

    assert "2 falhas de limpeza" in _texto_da_notificacao(executor)


def _desfazer_literal_applescript(script: str) -> str:
    """Lê o script como o AppleScript leria e devolve o texto da notificação.

    Reprova se o literal fecha antes da hora: aí o resto viraria comando.
    """
    prefixo, sufixo = 'display notification "', '" with title "antilixo"'
    assert script.startswith(prefixo)
    assert script.endswith(sufixo)
    miolo = script[len(prefixo) : -len(sufixo)]
    texto: list[str] = []
    escapando = False
    for caractere in miolo:
        if escapando:
            texto.append(caractere)
            escapando = False
        elif caractere == "\\":
            escapando = True
        else:
            assert caractere != '"', f"aspas sem escape em {miolo!r}"
            texto.append(caractere)
    assert not escapando
    return "".join(texto)


def test_nome_com_aspas_e_barra_nao_quebra_nem_injeta_comando() -> None:
    executor = ExecutorFalso()
    nome = 'x\\" & (do shell script "rm -rf ~") & "'
    cache = Achado(Categoria.CACHE, PurePath("/Users/u/.cache/uv") / nome, 10, "cache")
    resultado = ResultadoDaLimpeza(falhas=(FalhaDeLimpeza(cache, "PermissionError"),))

    _ = notificar(_veredito(), resultado, executor)

    texto = _desfazer_literal_applescript(_texto_da_notificacao(executor))
    assert texto == f"falha ao limpar {nome}"


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [("raise SystemExit(0)", True), ("raise SystemExit(3)", False)],
    ids=["sucesso", "saida-nao-zero"],
)
def test_executor_real_devolve_se_o_comando_deu_certo(codigo: str, *, esperado: bool) -> None:
    executor = ExecutorDeSubprocesso()

    assert executor.executar([sys.executable, "-c", codigo]) is esperado


def test_executor_real_desiste_no_timeout() -> None:
    executor = ExecutorDeSubprocesso(timeout_s=0.2)
    trava = "import threading; threading.Event().wait()"

    assert executor.executar([sys.executable, "-c", trava]) is False


def test_executor_real_sem_o_programa_devolve_falso(tmp_path: Path) -> None:
    executor = ExecutorDeSubprocesso()

    assert executor.executar([str(tmp_path / "nao-existe")]) is False
