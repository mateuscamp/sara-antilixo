"""Coletor de dados de apps desinstalados na ~/Library (órfãos, AGENTS.md)."""

import plistlib
from pathlib import Path

import pytest

from antilixo.coletores.library import coletar_orfaos_library
from antilixo.dominio.excecoes_library import EXCECOES_LIBRARY
from antilixo.dominio.modelo import Achado, Categoria


def _instalar_app(pasta_de_apps: Path, nome: str, bundle_id: str) -> Path:
    contents = pasta_de_apps / f"{nome}.app" / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as arquivo:
        plistlib.dump({"CFBundleIdentifier": bundle_id}, arquivo)
    return pasta_de_apps / f"{nome}.app"


def _dados(home: Path, subpasta: str, nome: str, tamanho: int = 10) -> Path:
    pasta = home / "Library" / subpasta / nome
    pasta.mkdir(parents=True)
    _ = (pasta / "dados.bin").write_bytes(b"d" * tamanho)
    return pasta


def test_pasta_de_app_desinstalado_vira_orfao(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    apps.mkdir()
    orfa = _dados(home, "Application Support", "com.unity3d.UnityEditor", 70)

    achados = coletar_orfaos_library(home, (apps,))

    assert achados == (
        Achado(
            Categoria.ORFAO_LIBRARY,
            orfa,
            70,
            "com.unity3d.UnityEditor sem app instalado (Application Support)",
        ),
    )


def test_pasta_de_app_instalado_nao_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Unity", "com.unity3d.UnityEditor")
    _ = _dados(home, "Application Support", "com.unity3d.UnityEditor")

    assert coletar_orfaos_library(home, (apps,)) == ()


@pytest.mark.parametrize(
    "conteudo",
    [
        b"isto nao e plist",
        plistlib.dumps({"CFBundleName": "Sem id"}),
        plistlib.dumps({"CFBundleIdentifier": 42}),
        plistlib.dumps(["lista", "e nao dicionario"]),
        None,
    ],
    ids=["lixo", "sem-id", "id-nao-texto", "nao-dicionario", "sem-info-plist"],
)
def test_plist_ilegivel_e_ignorado_sem_derrubar_a_coleta(
    tmp_path: Path, conteudo: bytes | None
) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Unity", "com.unity3d.UnityEditor")
    quebrado = apps / "Quebrado.app" / "Contents"
    quebrado.mkdir(parents=True)
    if conteudo is not None:
        _ = (quebrado / "Info.plist").write_bytes(conteudo)
    _ = _dados(home, "Application Support", "com.unity3d.UnityEditor")
    orfa = _dados(home, "Application Support", "com.exemplo.Sumiu")

    achados = coletar_orfaos_library(home, (apps,))

    assert [a.caminho for a in achados] == [orfa]


PASTAS_DA_LIBRARY = (
    "Application Support",
    "Caches",
    "Containers",
    "Saved Application State",
    "HTTPStorages",
    "WebKit",
    "Logs",
)


@pytest.mark.parametrize("subpasta", PASTAS_DA_LIBRARY)
def test_orfao_e_procurado_em_cada_pasta_da_library(tmp_path: Path, subpasta: str) -> None:
    home = tmp_path / "home"
    for outra in PASTAS_DA_LIBRARY:
        (home / "Library" / outra).mkdir(parents=True)
    orfa = home / "Library" / subpasta / "com.exemplo.Sumiu"
    orfa.mkdir()

    achados = coletar_orfaos_library(home, ())

    assert [(a.caminho, a.motivo) for a in achados] == [
        (orfa, f"com.exemplo.Sumiu sem app instalado ({subpasta})")
    ]


def test_pasta_da_library_ausente_nao_derruba_a_coleta(tmp_path: Path) -> None:
    home = tmp_path / "home"
    orfa = _dados(home, "Logs", "com.exemplo.Sumiu")

    achados = coletar_orfaos_library(home, ())

    assert [a.caminho for a in achados] == [orfa]


def test_symlink_na_library_nao_e_orfao(tmp_path: Path) -> None:
    # O destino pode estar fora da ~/Library; avisar sobre ele seria medir outra coisa.
    home = tmp_path / "home"
    fora = tmp_path / "externo"
    fora.mkdir()
    (home / "Library" / "Caches").mkdir(parents=True)
    (home / "Library" / "Caches" / "com.exemplo.Atalho").symlink_to(fora)

    assert coletar_orfaos_library(home, ()) == ()


@pytest.mark.parametrize("nome", ["Notion", "Comet", "Tibia", "1.2.3"])
def test_pasta_com_nome_sem_app_correspondente_e_orfa(tmp_path: Path, nome: str) -> None:
    # Regra (a) de 2026-11-09: substitui "pasta sem forma de bundle id é ignorada".
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Outro", "com.exemplo.Outro")
    orfa = _dados(home, "Application Support", nome, 12)

    achados = coletar_orfaos_library(home, (apps,))

    assert achados == (
        Achado(
            Categoria.ORFAO_LIBRARY, orfa, 12, f"{nome} sem app instalado (Application Support)"
        ),
    )


def _instalar_app_com_nomes(pasta_de_apps: Path, arquivo: str, nomes: dict[str, str]) -> None:
    contents = pasta_de_apps / f"{arquivo}.app" / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as saida:
        plistlib.dump({"CFBundleIdentifier": "com.exemplo.qualquer", **nomes}, saida)


@pytest.mark.parametrize(
    ("arquivo", "nomes", "pasta"),
    [
        ("Notion", {}, "Notion"),
        ("Notion", {}, "notion"),
        ("Navegador", {"CFBundleName": "Comet"}, "Comet"),
        ("Navegador", {"CFBundleDisplayName": "Tibia"}, "TIBIA"),
    ],
    ids=["nome-do-app", "nome-do-app-minusculo", "cfbundlename", "cfbundledisplayname"],
)
def test_pasta_com_nome_de_app_instalado_nao_e_orfa(
    tmp_path: Path, arquivo: str, nomes: dict[str, str], pasta: str
) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _instalar_app_com_nomes(apps, arquivo, nomes)
    _ = _dados(home, "Caches", pasta)

    assert coletar_orfaos_library(home, (apps,)) == ()


def test_pasta_da_apple_nunca_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _ = _dados(home, "Caches", "com.apple.Safari")
    _ = _dados(home, "Containers", "com.apple.mail")

    assert coletar_orfaos_library(home, ()) == ()


@pytest.mark.parametrize("nome", sorted(EXCECOES_LIBRARY))
def test_pasta_da_lista_de_excecoes_nunca_e_orfa(tmp_path: Path, nome: str) -> None:
    home = tmp_path / "home"
    _ = _dados(home, "Caches", nome)

    assert coletar_orfaos_library(home, ()) == ()


def test_pasta_com_prefixo_de_app_instalado_nao_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Code", "com.microsoft.VSCode")
    _ = _dados(home, "Caches", "com.microsoft.VSCode.ShipIt")
    sem_ponto = _dados(home, "Caches", "com.microsoft.VSCodeInsiders")

    achados = coletar_orfaos_library(home, (apps,))

    assert [a.caminho for a in achados] == [sem_ponto]


def test_comparacao_com_app_instalado_ignora_maiusculas(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Unity", "com.unity3d.UnityEditor")
    _ = _dados(home, "Caches", "com.Unity3D.unityeditor")

    assert coletar_orfaos_library(home, (apps,)) == ()


def _instalar_bundle(caminho: Path, bundle_id: str) -> None:
    (caminho / "Contents").mkdir(parents=True)
    with (caminho / "Contents" / "Info.plist").open("wb") as arquivo:
        plistlib.dump({"CFBundleIdentifier": bundle_id}, arquivo)


@pytest.mark.parametrize(
    "relativo",
    [
        "Utilities/Ferramenta.app",
        "Microsoft Office/Microsoft Word.app",
        "Dropbox.app/Contents/PlugIns/Garcon.appex",
        "Dropbox.app/Contents/Library/LoginItems/Ajudante.app",
    ],
    ids=["utilities", "pasta-do-fornecedor", "appex", "login-item"],
)
def test_app_em_subpasta_ou_aninhado_conta_como_instalado(tmp_path: Path, relativo: str) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Dropbox", "com.getdropbox.dropbox")
    _instalar_bundle(apps / relativo, "com.exemplo.aninhado")
    _ = _dados(home, "Containers", "com.exemplo.aninhado")

    assert coletar_orfaos_library(home, (apps,)) == ()
