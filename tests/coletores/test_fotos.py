"""Coletor de bibliotecas do Fotos presas em pasta sincronizada com a nuvem."""

import errno
import logging
from pathlib import Path

import pytest

from antilixo.coletores.fotos import coletar_fotos_em_nuvem, resumir_pastas_nao_lidas
from antilixo.dominio.modelo import Achado, Categoria


def _biblioteca(caminho: Path, tamanho: int) -> Path:
    (caminho / "originals").mkdir(parents=True)
    _ = (caminho / "originals" / "IMG_0001.heic").write_bytes(b"f" * tamanho)
    return caminho


def test_biblioteca_no_icloud_drive_vira_achado(tmp_path: Path) -> None:
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    biblioteca = _biblioteca(icloud / "Fotos" / "Antiga.photoslibrary", 4096 * 3)

    achados = coletar_fotos_em_nuvem(tmp_path).achados

    assert achados == (
        Achado(
            Categoria.FOTOS_EM_NUVEM,
            biblioteca,
            4096 * 3,
            "biblioteca do Fotos dentro de pasta sincronizada: Mobile Documents",
        ),
    )


def test_biblioteca_no_cloudstorage_vira_achado(tmp_path: Path) -> None:
    proton = tmp_path / "Library" / "CloudStorage" / "ProtonDrive-eu@proton.me-folder"
    biblioteca = _biblioteca(proton / "Fotos.photoslibrary", 40)

    achados = coletar_fotos_em_nuvem(tmp_path).achados

    assert [(a.caminho, a.motivo) for a in achados] == [
        (biblioteca, "biblioteca do Fotos dentro de pasta sincronizada: CloudStorage")
    ]


def test_nao_procura_biblioteca_dentro_de_outra(tmp_path: Path) -> None:
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    externa = _biblioteca(icloud / "Externa.photoslibrary", 4096 * 2)
    _ = _biblioteca(externa / "resources" / "Interna.photoslibrary", 4096)

    achados = coletar_fotos_em_nuvem(tmp_path).achados

    assert [(a.caminho, a.tamanho_bytes) for a in achados] == [(externa, 4096 * 3)]


def test_biblioteca_fora_das_pastas_sincronizadas_nao_vira_achado(tmp_path: Path) -> None:
    _ = _biblioteca(tmp_path / "Pictures" / "Photos Library.photoslibrary", 10)

    assert coletar_fotos_em_nuvem(tmp_path).achados == ()


def test_pasta_sincronizada_ilegivel_fica_no_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Sob o launchd, o TCC do macOS nega a leitura do iCloud Drive sem aviso; o walk engolia o
    # erro e os 5,8 GB de Fotos passariam calados (verificação real de 2026-11-09).
    trancada = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    trancada.mkdir(parents=True)
    trancada.chmod(0o000)
    try:
        achados = coletar_fotos_em_nuvem(tmp_path).achados
    finally:
        trancada.chmod(0o700)

    assert achados == ()
    assert "com~apple~CloudDocs" in caplog.text


def test_pasta_sincronizada_ausente_nao_suja_o_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert coletar_fotos_em_nuvem(tmp_path).achados == ()
    assert caplog.text == ""


def test_pastas_ilegiveis_viram_uma_linha_por_raiz(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Verificação real de 2026-11-09: 2.531 linhas de log por semana, uma por pasta.
    dropbox = tmp_path / "Library" / "CloudStorage" / "Dropbox"
    trancadas = [dropbox / "a", dropbox / "b"]
    for pasta in trancadas:
        pasta.mkdir(parents=True)
        pasta.chmod(0o000)
    try:
        leitura = coletar_fotos_em_nuvem(tmp_path)
    finally:
        for pasta in trancadas:
            pasta.chmod(0o700)

    assert leitura.nao_lidas == ("CloudStorage/Dropbox: 2 pastas sem permissão",)
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_raiz_bloqueada_inteira_diz_sem_permissao(tmp_path: Path) -> None:
    google = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-eu@gmail.com"
    google.mkdir(parents=True)
    google.chmod(0o000)
    try:
        leitura = coletar_fotos_em_nuvem(tmp_path)
    finally:
        google.chmod(0o700)

    assert leitura.nao_lidas == (
        "CloudStorage/GoogleDrive-eu@gmail.com: sem permissão para ler (Privacidade do macOS)",
    )


def test_pastas_so_na_nuvem_sao_resumidas_como_nao_baixadas(tmp_path: Path) -> None:
    raiz = tmp_path / "Dropbox"
    erros = [
        OSError(errno.EDEADLK, "Resource deadlock avoided", str(raiz / nome)) for nome in "xyz"
    ]

    assert resumir_pastas_nao_lidas("CloudStorage/Dropbox", raiz, erros) == (
        "CloudStorage/Dropbox: 3 pastas só na nuvem, não baixadas",
    )


def test_cada_conta_resume_so_as_proprias_pastas(tmp_path: Path) -> None:
    nuvem = tmp_path / "Library" / "CloudStorage"
    trancada = nuvem / "Dropbox" / "a"
    trancada.mkdir(parents=True)
    (nuvem / "ProtonDrive-eu-folder" / "fotos").mkdir(parents=True)
    trancada.chmod(0o000)
    try:
        leitura = coletar_fotos_em_nuvem(tmp_path)
    finally:
        trancada.chmod(0o700)

    assert leitura.nao_lidas == ("CloudStorage/Dropbox: 1 pasta sem permissão",)
