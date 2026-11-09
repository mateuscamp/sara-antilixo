import json
import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from antilixo.dominio.modelo import AvisoAnterior, Categoria, Estado, MedicaoDeDisco
from antilixo.relatorio.estado_em_disco import escrever_atomico, gravar_estado, ler_estado


def _estado_preenchido() -> Estado:
    return Estado(
        avisos_anteriores=(
            AvisoAnterior(Categoria.PROJETO_PARADO, 123),
            AvisoAnterior(Categoria.CACHE, 0),
        ),
        ultima_limpeza=date(2026, 11, 1),
        medicoes=(
            MedicaoDeDisco(date(2026, 11, 9), 456),
            MedicaoDeDisco(date(2026, 11, 8), 0),
        ),
    )


def test_arquivo_ausente_devolve_estado_vazio(tmp_path: Path) -> None:
    assert ler_estado(tmp_path, hoje=date(2026, 11, 9)) == Estado()


def test_escrita_cria_pasta_mae_e_grava_utf8(tmp_path: Path) -> None:
    destino = tmp_path / "pasta" / "aninhada" / "estado.json"

    escrever_atomico(destino, "conteúdo\n")

    assert destino.is_file()
    assert destino.read_bytes() == "conteúdo\n".encode()


def test_falha_de_codificacao_preserva_destino_e_temporario_e_repermite_escrita(
    tmp_path: Path,
) -> None:
    destino = tmp_path / "estado.json"
    _ = destino.write_text("anterior", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        escrever_atomico(destino, "\ud800")

    assert destino.read_text(encoding="utf-8") == "anterior"
    temporario = tmp_path / "estado.json.tmp"
    assert temporario.is_file()

    escrever_atomico(destino, "novo")

    assert destino.read_text(encoding="utf-8") == "novo"
    assert not temporario.exists()


def test_gravacao_usa_formato_json_versionado_indentado_com_quebra_final(tmp_path: Path) -> None:
    gravar_estado(tmp_path, _estado_preenchido())

    destino = tmp_path / "estado.json"
    assert destino.is_file()
    assert destino.read_text(encoding="utf-8") == (
        '{\n  "versao": 1,\n  "avisos_anteriores": [\n'
        '    {\n      "categoria": "projeto-parado",\n      "total_bytes_no_aviso": 123\n    },\n'
        '    {\n      "categoria": "cache",\n      "total_bytes_no_aviso": 0\n    }\n  ],\n'
        '  "ultima_limpeza": "2026-11-01",\n  "medicoes": [\n'
        '    {\n      "dia": "2026-11-09",\n      "usado_bytes": 456\n    },\n'
        '    {\n      "dia": "2026-11-08",\n      "usado_bytes": 0\n    }\n  ]\n}\n'
    )


@pytest.mark.parametrize("estado", [_estado_preenchido(), Estado()], ids=["completo", "vazio"])
def test_gravacao_e_leitura_preservam_estado_exato(tmp_path: Path, estado: Estado) -> None:
    gravar_estado(tmp_path, estado)

    assert ler_estado(tmp_path, hoje=date(2026, 11, 9)) == estado


def _documento(
    *,
    versao: object = 1,
    avisos: object = (),
    ultima_limpeza: object = None,
    medicoes: object = (),
) -> bytes:
    return json.dumps(
        {
            "versao": versao,
            "avisos_anteriores": avisos,
            "ultima_limpeza": ultima_limpeza,
            "medicoes": medicoes,
        }
    ).encode("utf-8")


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(b"{ invalido", id="json-invalido"),
        pytest.param(b"\xff\xfe", id="utf8-invalido"),
        pytest.param(b"[]", id="raiz-lista"),
        pytest.param(b"null", id="raiz-nula"),
        pytest.param(b"true", id="raiz-booleana"),
        pytest.param(b'"texto"', id="raiz-string"),
        pytest.param(b"123", id="raiz-numero"),
        pytest.param(b"{}", id="sem-versao"),
        pytest.param(b'{"versao": 1}', id="sem-ultima-limpeza"),
        pytest.param(b'{"versao": 1, "ultima_limpeza": null}', id="sem-avisos"),
        pytest.param(
            b'{"versao": 1, "ultima_limpeza": null, "avisos_anteriores": []}',
            id="sem-medicoes",
        ),
        pytest.param(_documento(versao=2), id="versao-desconhecida"),
        pytest.param(_documento(versao=True), id="versao-booleana"),
        pytest.param(_documento(versao=1.0), id="versao-float"),
        pytest.param(_documento(versao="1"), id="versao-string"),
        pytest.param(_documento(avisos=None), id="avisos-nulos"),
        pytest.param(_documento(avisos={}), id="avisos-objeto"),
        pytest.param(_documento(avisos="cache"), id="avisos-string"),
        pytest.param(_documento(avisos=[None]), id="aviso-nao-objeto"),
        pytest.param(_documento(avisos=[dict[str, object]()]), id="aviso-sem-categoria"),
        pytest.param(_documento(avisos=[{"categoria": "cache"}]), id="aviso-sem-total"),
        pytest.param(
            _documento(avisos=[{"categoria": "desconhecida", "total_bytes_no_aviso": 1}]),
            id="categoria-desconhecida",
        ),
        pytest.param(
            _documento(avisos=[{"categoria": 1, "total_bytes_no_aviso": 1}]),
            id="categoria-nao-string",
        ),
        pytest.param(
            _documento(avisos=[{"categoria": "cache", "total_bytes_no_aviso": True}]),
            id="aviso-total-booleano",
        ),
        pytest.param(
            _documento(avisos=[{"categoria": "cache", "total_bytes_no_aviso": -1}]),
            id="aviso-total-negativo",
        ),
        pytest.param(
            _documento(avisos=[{"categoria": "cache", "total_bytes_no_aviso": 1.5}]),
            id="aviso-total-float",
        ),
        pytest.param(_documento(ultima_limpeza=True), id="limpeza-nao-string"),
        pytest.param(_documento(ultima_limpeza="20261101"), id="limpeza-data-compacta"),
        pytest.param(_documento(ultima_limpeza="2026-W45-1"), id="limpeza-semana-iso"),
        pytest.param(_documento(ultima_limpeza="2026-02-30"), id="limpeza-data-impossivel"),
        pytest.param(_documento(ultima_limpeza="2026-11-01T00:00:00"), id="limpeza-data-com-hora"),
        pytest.param(_documento(medicoes=None), id="medicoes-nulas"),
        pytest.param(_documento(medicoes={}), id="medicoes-objeto"),
        pytest.param(_documento(medicoes=[list[object]()]), id="medicao-nao-objeto"),
        pytest.param(_documento(medicoes=[dict[str, object]()]), id="medicao-sem-dia"),
        pytest.param(_documento(medicoes=[{"dia": "2026-11-09"}]), id="medicao-sem-usado"),
        pytest.param(_documento(medicoes=[{"dia": None, "usado_bytes": 1}]), id="medicao-dia-nulo"),
        pytest.param(
            _documento(medicoes=[{"dia": "20261109", "usado_bytes": 1}]),
            id="medicao-data-compacta",
        ),
        pytest.param(
            _documento(medicoes=[{"dia": "2026-02-30", "usado_bytes": 1}]),
            id="medicao-data-impossivel",
        ),
        pytest.param(
            _documento(medicoes=[{"dia": "2026-11-09", "usado_bytes": False}]),
            id="medicao-usado-booleano",
        ),
        pytest.param(
            _documento(medicoes=[{"dia": "2026-11-09", "usado_bytes": -1}]),
            id="medicao-usado-negativo",
        ),
        pytest.param(
            _documento(medicoes=[{"dia": "2026-11-09", "usado_bytes": "1"}]),
            id="medicao-usado-string",
        ),
    ],
)
def test_conteudo_corrompido_e_preservado_com_data_e_devolve_estado_vazio(
    tmp_path: Path, conteudo: bytes
) -> None:
    destino = tmp_path / "estado.json"
    _ = destino.write_bytes(conteudo)

    assert ler_estado(tmp_path, hoje=date(2030, 2, 3)) == Estado()

    corrompido = tmp_path / "estado.json.corrompido-20300203"
    assert corrompido.is_file()
    assert corrompido.read_bytes() == conteudo
    assert not destino.exists()


def test_corrupcoes_no_mesmo_dia_ganham_sufixos_sem_sobrescrever_anteriores(tmp_path: Path) -> None:
    destino = tmp_path / "estado.json"
    hoje = date(2026, 11, 9)
    anteriores: list[tuple[Path, bytes]] = []

    for sufixo, conteudo in [("", b"primeiro"), ("-2", b"segundo"), ("-3", b"terceiro")]:
        _ = destino.write_bytes(conteudo)

        assert ler_estado(tmp_path, hoje=hoje) == Estado()

        anteriores.append((tmp_path / f"estado.json.corrompido-20261109{sufixo}", conteudo))
        for caminho, original in anteriores:
            assert caminho.read_bytes() == original


def test_corrupcao_registra_warning_com_caminho_novo_valor_e_formato_esperado(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _ = (tmp_path / "estado.json").write_bytes(_documento(versao=2))
    primeiro = tmp_path / "estado.json.corrompido-20261109"
    _ = primeiro.write_bytes(b"anterior")

    with caplog.at_level(logging.WARNING, logger="antilixo.relatorio.estado_em_disco"):
        assert ler_estado(tmp_path, hoje=date(2026, 11, 9)) == Estado()

    assert len(caplog.records) == 1
    registro = caplog.records[0]
    assert registro.name == "antilixo.relatorio.estado_em_disco"
    assert registro.levelno == logging.WARNING
    assert str(tmp_path / "estado.json.corrompido-20261109-2") in registro.getMessage()
    assert "Recebido 2" in registro.getMessage()
    assert "esperado versao igual a 1" in registro.getMessage()


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(b'{"versao": ' + b"1" * 5000 + b"}", id="inteiro-gigante"),
        pytest.param(b"[" * 100_000 + b"]" * 100_000, id="aninhamento-profundo"),
    ],
)
def test_json_que_o_parser_recusa_nao_trava_a_execucao(tmp_path: Path, conteudo: bytes) -> None:
    # O json levanta ValueError (limite de dígitos) ou RecursionError, não JSONDecodeError.
    _ = (tmp_path / "estado.json").write_bytes(conteudo)

    estado = ler_estado(tmp_path, hoje=date(2026, 11, 9))

    assert estado == Estado()
    assert (tmp_path / "estado.json.corrompido-20261109").read_bytes() == conteudo


def test_temporario_plantado_como_symlink_falha_sem_sobrescrever_o_alvo(tmp_path: Path) -> None:
    # Achado A1 da auditoria de 2026-11-09: open("w") seguia o symlink e escrevia fora da pasta.
    importante = tmp_path / "importante.txt"
    _ = importante.write_text("não sobrescreva", encoding="utf-8")
    pasta = tmp_path / "estado"
    pasta.mkdir()
    (pasta / "relatorio.md.tmp").symlink_to(importante)

    with pytest.raises(OSError, match=r"symbolic link|Too many levels"):
        escrever_atomico(pasta / "relatorio.md", "# relatório\n")

    assert importante.read_text(encoding="utf-8") == "não sobrescreva"
    assert not (pasta / "relatorio.md").exists()


def _pasta_no_lugar(destino: Path) -> Path:
    destino.mkdir()
    dentro = destino / "dentro"
    _ = dentro.write_text("x", encoding="utf-8")
    return dentro


def _sem_permissao(destino: Path) -> Path:
    _ = destino.write_text("{}", encoding="utf-8")
    destino.chmod(0o000)
    return destino


@pytest.mark.parametrize(
    "preparar", [_pasta_no_lugar, _sem_permissao], ids=["pasta-no-lugar", "sem-permissao"]
)
def test_estado_ilegivel_devolve_vazio_sem_renomear_nem_apagar(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, preparar: Callable[[Path], Path]
) -> None:
    # Achado A2 da auditoria de 2026-11-09: OSError na leitura travava toda execução semanal.
    preservado = preparar(tmp_path / "estado.json")

    with caplog.at_level(logging.WARNING, logger="antilixo.relatorio.estado_em_disco"):
        estado = ler_estado(tmp_path, hoje=date(2026, 11, 9))

    assert estado == Estado()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["estado.json"]
    assert preservado.exists()
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
