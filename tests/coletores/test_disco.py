"""Medidas de disco compartilhadas pelos coletores."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from antilixo.coletores.disco import medir_uso_do_disco, somar_tamanho


@pytest.fixture
def pasta_trancada(tmp_path: Path) -> Iterator[Path]:
    trancada = tmp_path / "trancada"
    trancada.mkdir()
    _ = (trancada / "segredo.bin").write_bytes(b"s" * 999)
    trancada.chmod(0o000)
    yield trancada
    trancada.chmod(0o700)  # sem isso o pytest não consegue limpar o tmp_path


def test_somar_tamanho_pula_pasta_sem_permissao(tmp_path: Path, pasta_trancada: Path) -> None:
    _ = (tmp_path / "visivel.bin").write_bytes(b"v" * 10)

    assert pasta_trancada.is_dir()
    assert somar_tamanho(tmp_path) == 10


def test_medir_uso_do_disco_bate_com_o_disk_usage(tmp_path: Path) -> None:
    # Oráculo independente: shutil.disk_usage (o teste pode importar shutil; src/ não pode).
    # O volume é o real e muda entre as duas leituras: tolerância de 64 MB.
    esperado = shutil.disk_usage(tmp_path).used

    medido = medir_uso_do_disco(tmp_path)

    assert abs(medido - esperado) < 64 * 1024 * 1024
