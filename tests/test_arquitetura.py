"""Fitness functions de arquitetura do ADR-0001."""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import override

PACOTE = Path(__file__).resolve().parents[1] / "src" / "antilixo"

# Nomes de chamada que apagam: shutil.rmtree, Path.unlink/rmdir, os.remove/unlink/rmdir/removedirs.
# O import-linter só barra `shutil` fora de acoes/; Path e os passam por ele.
# TemporaryDirectory e NamedTemporaryFile apagam por dentro (rmtree/unlink no fim do contexto):
# entraram depois que um gravar_estado com TemporaryDirectory passou pelos dois (2026-11-09).
_APAGAM = frozenset(
    {
        "rmtree",
        "unlink",
        "rmdir",
        "remove",
        "removedirs",
        "TemporaryDirectory",
        "NamedTemporaryFile",
    }
)


@dataclass(frozen=True, slots=True)
class ChamadaQueApaga:
    arquivo: Path
    linha: int
    nome: str

    @override
    def __str__(self) -> str:
        return f"{self.arquivo}:{self.linha}: {self.nome}()"


def _nome_chamado(chamada: ast.Call) -> str | None:
    funcao = chamada.func
    if isinstance(funcao, ast.Attribute):
        return funcao.attr
    if isinstance(funcao, ast.Name):
        return funcao.id
    return None


def chamadas_que_apagam(pacote: Path) -> list[ChamadaQueApaga]:
    """Toda chamada a um nome de `_APAGAM` em `pacote`, fora da pasta `acoes/`."""
    acoes = pacote / "acoes"
    return [
        ChamadaQueApaga(arquivo, no.lineno, nome)
        for arquivo in sorted(pacote.rglob("*.py"))
        if not arquivo.is_relative_to(acoes)
        for no in ast.walk(ast.parse(arquivo.read_text(), filename=str(arquivo)))
        if isinstance(no, ast.Call) and (nome := _nome_chamado(no)) is not None and nome in _APAGAM
    ]


def test_so_acoes_apaga_arquivos() -> None:
    assert [str(c) for c in chamadas_que_apagam(PACOTE)] == []


_PLANTADO = """import os
import shutil
import tempfile
from os import remove
from pathlib import Path


def varrer(p: Path) -> None:
    shutil.rmtree(p)
    p.unlink()
    p.rmdir()
    os.remove(p)
    os.removedirs(p)
    remove(p)
    p.exists()
    tempfile.TemporaryDirectory(dir=p)
    tempfile.NamedTemporaryFile(dir=p)
"""


def test_detector_acha_cada_forma_de_apagar_fora_de_acoes(tmp_path: Path) -> None:
    # Sem este teste, um detector que nunca acha nada deixaria test_so_acoes_apaga_arquivos verde.
    for pasta in ("coletores", "acoes"):
        (tmp_path / pasta).mkdir()
        _ = (tmp_path / pasta / "plantado.py").write_text(_PLANTADO)

    achadas = chamadas_que_apagam(tmp_path)

    plantado = tmp_path / "coletores" / "plantado.py"
    assert [(c.arquivo, c.linha, c.nome) for c in achadas] == [
        (plantado, 9, "rmtree"),
        (plantado, 10, "unlink"),
        (plantado, 11, "rmdir"),
        (plantado, 12, "remove"),
        (plantado, 13, "removedirs"),
        (plantado, 14, "remove"),
        (plantado, 16, "TemporaryDirectory"),
        (plantado, 17, "NamedTemporaryFile"),
    ]
