"""Coletor de dados de apps desinstalados na ~/Library (órfãos, AGENTS.md)."""

import logging
import plistlib
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import override

import pytest

from antilixo.coletores.library import coletar_orfaos_library
from antilixo.dominio.excecoes_library import EXCECOES_LIBRARY, Excecao
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
    orfa = _dados(home, "Application Support", "com.unity3d.UnityEditor", 4096 * 2)

    achados = coletar_orfaos_library(home, (apps,)).achados

    assert achados == (
        Achado(
            Categoria.ORFAO_LIBRARY,
            orfa,
            4096 * 2,
            "com.unity3d.UnityEditor sem app instalado (Application Support)",
        ),
    )


def test_pasta_de_app_instalado_nao_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Unity", "com.unity3d.UnityEditor")
    _ = _dados(home, "Application Support", "com.unity3d.UnityEditor")

    assert coletar_orfaos_library(home, (apps,)).achados == ()


@pytest.mark.parametrize(
    "conteudo",
    [
        b"isto nao e plist",
        b'<?xml version="1.0"?><plist><dict><key>CFBundleIdentifier',
        plistlib.dumps({"CFBundleName": "Sem id"}),
        plistlib.dumps({"CFBundleIdentifier": 42}),
        plistlib.dumps(["lista", "e nao dicionario"]),
        None,
    ],
    ids=["lixo", "xml-truncado", "sem-id", "id-nao-texto", "nao-dicionario", "sem-info-plist"],
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

    achados = coletar_orfaos_library(home, (apps,)).achados

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

    achados = coletar_orfaos_library(home, ()).achados

    assert [(a.caminho, a.motivo) for a in achados] == [
        (orfa, f"com.exemplo.Sumiu sem app instalado ({subpasta})")
    ]


def test_pasta_da_library_ausente_nao_derruba_a_coleta(tmp_path: Path) -> None:
    home = tmp_path / "home"
    orfa = _dados(home, "Logs", "com.exemplo.Sumiu")

    achados = coletar_orfaos_library(home, ()).achados

    assert [a.caminho for a in achados] == [orfa]


def test_symlink_na_library_nao_e_orfao(tmp_path: Path) -> None:
    # O destino pode estar fora da ~/Library; avisar sobre ele seria medir outra coisa.
    home = tmp_path / "home"
    fora = tmp_path / "externo"
    fora.mkdir()
    (home / "Library" / "Caches").mkdir(parents=True)
    (home / "Library" / "Caches" / "com.exemplo.Atalho").symlink_to(fora)

    assert coletar_orfaos_library(home, ()).achados == ()


@pytest.mark.parametrize("nome", ["Notion", "Comet", "Tibia", "1.2.3"])
def test_pasta_com_nome_sem_app_correspondente_e_orfa(tmp_path: Path, nome: str) -> None:
    # Regra (a) de 2026-11-09: substitui "pasta sem forma de bundle id é ignorada".
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Outro", "com.exemplo.Outro")
    orfa = _dados(home, "Application Support", nome, 4096 * 3)

    achados = coletar_orfaos_library(home, (apps,)).achados

    assert achados == (
        Achado(
            Categoria.ORFAO_LIBRARY,
            orfa,
            4096 * 3,
            f"{nome} sem app instalado (Application Support)",
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

    assert coletar_orfaos_library(home, (apps,)).achados == ()


def test_pasta_da_apple_nunca_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _ = _dados(home, "Caches", "com.apple.Safari")
    _ = _dados(home, "Containers", "com.apple.mail")

    assert coletar_orfaos_library(home, ()).achados == ()


@pytest.mark.parametrize("excecao", EXCECOES_LIBRARY, ids=[e.nome for e in EXCECOES_LIBRARY])
def test_pasta_da_lista_de_excecoes_nunca_e_orfa(tmp_path: Path, excecao: Excecao) -> None:
    home = tmp_path / "home"
    for subpasta in excecao.pastas or {"Caches"}:
        _ = _dados(home, subpasta, excecao.nome)

    assert coletar_orfaos_library(home, ()).achados == ()


def test_excecao_de_nome_solto_nao_vale_fora_da_pasta_dela(tmp_path: Path) -> None:
    home = tmp_path / "home"
    homonima = _dados(home, "Application Support", "Databases")

    achados = coletar_orfaos_library(home, ()).achados

    assert [a.caminho for a in achados] == [homonima]


def test_pasta_com_prefixo_de_app_instalado_nao_e_orfa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Code", "com.microsoft.VSCode")
    _ = _dados(home, "Caches", "com.microsoft.VSCode.ShipIt")
    sem_ponto = _dados(home, "Caches", "com.microsoft.VSCodeInsiders")

    achados = coletar_orfaos_library(home, (apps,)).achados

    assert [a.caminho for a in achados] == [sem_ponto]


def test_comparacao_com_app_instalado_ignora_maiusculas(tmp_path: Path) -> None:
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "Unity", "com.unity3d.UnityEditor")
    _ = _dados(home, "Caches", "com.Unity3D.unityeditor")

    assert coletar_orfaos_library(home, (apps,)).achados == ()


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

    assert coletar_orfaos_library(home, (apps,)).achados == ()


@pytest.fixture
def caches_trancado(tmp_path: Path) -> Iterator[Path]:
    """~/Library/Caches que recusa a listagem, como o TCC faz sob o launchd."""
    caches = tmp_path / "home" / "Library" / "Caches"
    caches.mkdir(parents=True)
    caches.chmod(0o000)
    yield caches
    caches.chmod(0o700)


def test_pasta_da_library_sem_permissao_e_pulada_com_log(
    tmp_path: Path, caches_trancado: Path, caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "home"
    orfa = _dados(home, "Logs", "com.exemplo.Sumiu")

    with caplog.at_level(logging.WARNING, logger="antilixo.coletores.library"):
        achados = coletar_orfaos_library(home, ()).achados

    assert [a.caminho for a in achados] == [orfa]
    assert [r.getMessage() for r in caplog.records] == [
        f"sem permissão para listar, pasta pulada: {caches_trancado}"
    ]


class _PastaQueFalhaAoListar(Path):
    @override
    def iterdir(self) -> Generator[Path]:
        if self.name == "Caches":
            mensagem = f"Recebido {self}; esperado diretório legível."
            raise NotADirectoryError(mensagem)
        yield from super().iterdir()


def test_erro_de_listagem_pula_pasta_com_log_e_continua_coleta(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "home"
    caches = home / "Library" / "Caches"
    caches.mkdir(parents=True)
    orfa = _dados(home, "Logs", "com.exemplo.Sumiu")

    achados = coletar_orfaos_library(_PastaQueFalhaAoListar(home), ()).achados

    assert [a.caminho for a in achados] == [orfa]
    assert [r.name for r in caplog.records] == ["antilixo.coletores.library"]
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert str(caches) in caplog.text


def test_pasta_oculta_e_ignorada(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _ = _dados(home, "Caches", ".Oculta")
    _ = _dados(home, "Application Support", ".com.exemplo.Oculto")

    assert coletar_orfaos_library(home, ()).achados == ()


@pytest.mark.parametrize(
    ("bundle_id", "pasta"),
    [
        ("com.google.Chrome", "Google"),
        ("com.jetbrains.toolbox", "JetBrains"),
        ("com.Blizzard.Battle-net", "BLIZZARD"),
    ],
)
def test_pasta_com_nome_do_fornecedor_de_app_instalado_nao_e_orfa(
    tmp_path: Path, bundle_id: str, pasta: str
) -> None:
    # Regra do fornecedor (2026-11-09): o 2º rótulo do bundle id conta como nome do app.
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _ = _instalar_app(apps, "App", bundle_id)
    _ = _dados(home, "Application Support", pasta)
    outra = _dados(home, "Application Support", "Microsoft")

    achados = coletar_orfaos_library(home, (apps,)).achados

    assert [a.caminho for a in achados] == [outra]


def test_busca_de_apps_desce_no_maximo_duas_pastas_comuns(tmp_path: Path) -> None:
    # Regra (b2) de 2026-11-09: profundidade limitada para a varredura continuar rápida.
    home = tmp_path / "home"
    apps = tmp_path / "Applications"
    _instalar_bundle(apps / "Fornecedor" / "Suite" / "Raso.app", "com.exemplo.raso")
    _instalar_bundle(apps / "a" / "b" / "c" / "Fundo.app", "com.exemplo.fundo")
    _ = _dados(home, "Caches", "com.exemplo.raso")
    fundo = _dados(home, "Caches", "com.exemplo.fundo")

    achados = coletar_orfaos_library(home, (apps,)).achados

    assert [a.caminho for a in achados] == [fundo]


def test_pasta_da_library_bloqueada_vai_para_o_que_nao_deu_para_ler(
    tmp_path: Path, caches_trancado: Path
) -> None:
    # Achado da revisão de 2026-11-09: o log sozinho era um buraco calado no relatório.
    del caches_trancado
    leitura = coletar_orfaos_library(tmp_path / "home", ())

    assert leitura.nao_lidas == ("Library/Caches: sem permissão para ler (Privacidade do macOS)",)
