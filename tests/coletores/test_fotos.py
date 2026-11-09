"""Coletor de bibliotecas do Fotos presas em pasta sincronizada com a nuvem."""

from pathlib import Path

from antilixo.coletores.fotos import coletar_fotos_em_nuvem
from antilixo.dominio.modelo import Achado, Categoria


def _biblioteca(caminho: Path, tamanho: int) -> Path:
    (caminho / "originals").mkdir(parents=True)
    _ = (caminho / "originals" / "IMG_0001.heic").write_bytes(b"f" * tamanho)
    return caminho


def test_biblioteca_no_icloud_drive_vira_achado(tmp_path: Path) -> None:
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    biblioteca = _biblioteca(icloud / "Fotos" / "Antiga.photoslibrary", 300)

    achados = coletar_fotos_em_nuvem(tmp_path)

    assert achados == (
        Achado(
            Categoria.FOTOS_EM_NUVEM,
            biblioteca,
            300,
            "biblioteca do Fotos dentro de pasta sincronizada: Mobile Documents",
        ),
    )


def test_biblioteca_no_cloudstorage_vira_achado(tmp_path: Path) -> None:
    proton = tmp_path / "Library" / "CloudStorage" / "ProtonDrive-eu@proton.me-folder"
    biblioteca = _biblioteca(proton / "Fotos.photoslibrary", 40)

    achados = coletar_fotos_em_nuvem(tmp_path)

    assert [(a.caminho, a.motivo) for a in achados] == [
        (biblioteca, "biblioteca do Fotos dentro de pasta sincronizada: CloudStorage")
    ]


def test_nao_procura_biblioteca_dentro_de_outra(tmp_path: Path) -> None:
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    externa = _biblioteca(icloud / "Externa.photoslibrary", 10)
    _ = _biblioteca(externa / "resources" / "Interna.photoslibrary", 5)

    achados = coletar_fotos_em_nuvem(tmp_path)

    assert [(a.caminho, a.tamanho_bytes) for a in achados] == [(externa, 15)]


def test_biblioteca_fora_das_pastas_sincronizadas_nao_vira_achado(tmp_path: Path) -> None:
    _ = _biblioteca(tmp_path / "Pictures" / "Photos Library.photoslibrary", 10)

    assert coletar_fotos_em_nuvem(tmp_path) == ()
