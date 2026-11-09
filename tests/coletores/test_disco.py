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
    _ = (tmp_path / "visivel.bin").write_bytes(b"v" * 4096)

    assert pasta_trancada.is_dir()
    assert somar_tamanho(tmp_path) == 4096


def test_medir_uso_do_disco_bate_com_o_disk_usage(tmp_path: Path) -> None:
    # Oráculo independente: shutil.disk_usage (o teste pode importar shutil; src/ não pode).
    # O volume é o real e muda entre as duas leituras: tolerância de 64 MB.
    esperado = shutil.disk_usage(tmp_path).used

    medido = medir_uso_do_disco(tmp_path)

    assert abs(medido - esperado) < 64 * 1024 * 1024


@pytest.fixture
def pasta_sem_busca(tmp_path: Path) -> Iterator[Path]:
    """Pasta que lista os nomes mas recusa o lstat, como arquivo que some na varredura."""
    pasta = tmp_path / "sem-busca"
    pasta.mkdir()
    _ = (pasta / "some.bin").write_bytes(b"s" * 4096)
    pasta.chmod(0o400)
    yield pasta
    pasta.chmod(0o700)


def test_somar_tamanho_pula_arquivo_cujo_lstat_falha(tmp_path: Path, pasta_sem_busca: Path) -> None:
    assert pasta_sem_busca.is_dir()

    assert somar_tamanho(tmp_path) == 0


def test_somar_tamanho_conta_o_espaco_ocupado_e_nao_o_tamanho_aparente(tmp_path: Path) -> None:
    # Achado A4 de 2026-11-09: um Docker.raw esparso não pode aparecer com o tamanho aparente.
    esparso = tmp_path / "Docker.raw"
    with esparso.open("wb") as arquivo:
        _ = arquivo.seek(256 * 1024 * 1024)
        _ = arquivo.write(b"x")

    assert somar_tamanho(tmp_path) < 1024 * 1024


def test_somar_tamanho_conta_hardlink_uma_vez(tmp_path: Path) -> None:
    original = tmp_path / "a.bin"
    _ = original.write_bytes(b"h" * 64 * 1024)
    tamanho_de_um = somar_tamanho(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").hardlink_to(original)

    assert somar_tamanho(tmp_path) == tamanho_de_um
