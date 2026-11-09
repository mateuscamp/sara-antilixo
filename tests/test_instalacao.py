"""Fitness function do ADR-0001 (sobreviver à formatação): `./install.sh` idempotente.

Tudo roda com HOME em `tmp_path` e `uv`, `brew` e `launchctl` falsos no PATH: o teste nunca carrega
um LaunchAgent real nem toca o `~/.zshrc` real.
"""

import os
import plistlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install.sh"
ROTULO = "com.mateuscamp.sara-antilixo"

# O falso registra a chamada numa linha do log do teste. Os falsos são criados uma vez por sessão:
# o macOS confere todo executável novo na primeira execução (~0,4 s cada), e criá-los por teste
# estouraria os 10 s da suíte.
_FALSO = """#!/bin/bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FALSO_LOG"
{extra}
exit 0
"""
# O launchctl de verdade falha no bootout de agente que não está carregado.
_EXTRA_LAUNCHCTL = '[[ "$1" == bootout ]] && exit 3'
# O brew falso "instala" o uv falso numa pasta do PATH, como o brew de verdade faz.
_EXTRA_BREW = """if [[ "$1" == install && "$2" == uv ]]; then
  cp "$FALSO_UV" "$FALSO_INSTALADOS/uv"
  chmod +x "$FALSO_INSTALADOS/uv"
fi"""


@dataclass(frozen=True, slots=True)
class Falsos:
    """Uma pasta por executável falso, para cada teste montar o PATH com ou sem cada um."""

    uv: Path
    brew: Path
    launchctl: Path


@dataclass(frozen=True, slots=True)
class Caixa:
    """HOME temporário e PATH com executáveis falsos para rodar o install.sh isolado."""

    home: Path
    pasta: Path
    falsos: Falsos
    caminhos: tuple[Path, ...]

    @property
    def plist(self) -> Path:
        return self.home / "Library" / "LaunchAgents" / f"{ROTULO}.plist"

    @property
    def zshrc(self) -> Path:
        return self.home / ".zshrc"

    @property
    def estado(self) -> Path:
        return self.home / ".local" / "state" / "sara-antilixo"

    @property
    def instalados(self) -> Path:
        """Onde o brew falso põe o uv que instala."""
        return self.pasta / "instalados"

    def chamadas(self) -> list[str]:
        log = self.pasta / "chamadas.log"
        return log.read_text().splitlines() if log.exists() else []

    def ambiente(self) -> dict[str, str]:
        # Sem /opt/homebrew/bin: o uv e o brew de verdade ficam fora do alcance do install.sh.
        pastas = [*map(str, self.caminhos), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        return {
            "HOME": str(self.home),
            "PATH": ":".join(pastas),
            "FALSO_LOG": str(self.pasta / "chamadas.log"),
            "FALSO_UV": str(self.falsos.uv / "uv"),
            "FALSO_INSTALADOS": str(self.instalados),
        }


def _escrever_falso(pasta: Path, nome: str, extra: str = "") -> Path:
    pasta.mkdir()
    arquivo = pasta / nome
    _ = arquivo.write_text(_FALSO.format(extra=extra))
    arquivo.chmod(0o755)
    return pasta


@pytest.fixture(scope="session")
def falsos(tmp_path_factory: pytest.TempPathFactory) -> Falsos:
    raiz = tmp_path_factory.mktemp("falsos")
    return Falsos(
        uv=_escrever_falso(raiz / "uv", "uv"),
        brew=_escrever_falso(raiz / "brew", "brew", _EXTRA_BREW),
        launchctl=_escrever_falso(raiz / "launchctl", "launchctl", _EXTRA_LAUNCHCTL),
    )


def _caixa(raiz: Path, falsos: Falsos, *, com_uv: bool = True, com_brew: bool = True) -> Caixa:
    home = raiz / "home"
    pasta = raiz / "caixa"
    home.mkdir()
    pasta.mkdir()
    (pasta / "instalados").mkdir()
    caminhos = [pasta / "instalados", falsos.launchctl]
    if com_uv:
        caminhos.append(falsos.uv)
    if com_brew:
        caminhos.append(falsos.brew)
    return Caixa(home=home, pasta=pasta, falsos=falsos, caminhos=tuple(caminhos))


def _instalar(caixa: Caixa) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # motivo: executa o install.sh do próprio repo, sem shell
        ["/bin/bash", str(INSTALL)],
        env=caixa.ambiente(),
        capture_output=True,
        text=True,
        check=False,
    )


def _plist_valido(plist: Path) -> bool:
    """O mesmo verificador que o macOS usa; reprova XML malformado sem lançar exceção no teste."""
    resultado = subprocess.run(  # noqa: S603  # motivo: plutil do sistema, caminho absoluto, sem shell
        ["/usr/bin/plutil", "-lint", str(plist)], capture_output=True, check=False
    )
    return resultado.returncode == 0


def _ler_plist(plist: Path) -> object:
    lido = plistlib.loads(plist.read_bytes())  # pyright: ignore[reportAny]  # motivo: plistlib devolve Any
    return cast("object", lido)  # motivo: object é o tipo topo; o teste só compara com ==


def _agente_esperado(caixa: Caixa, uv: Path) -> dict[str, object]:
    log = str(caixa.estado / "launchd.log")
    return {
        "Label": ROTULO,
        "ProgramArguments": [
            str(uv),
            "run",
            "--locked",
            "--project",
            str(REPO),
            "python",
            "-m",
            "antilixo",
        ],
        "StartCalendarInterval": {"Weekday": 0, "Hour": 10, "Minute": 0},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


@pytest.fixture
def caixa(tmp_path: Path, falsos: Falsos) -> Caixa:
    return _caixa(tmp_path, falsos)


def test_install_escreve_agente_semanal_com_uv_absoluto(caixa: Caixa) -> None:
    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    assert caixa.plist.is_file()
    assert _ler_plist(caixa.plist) == _agente_esperado(caixa, caixa.falsos.uv / "uv")


def test_install_escapa_caminho_com_caracteres_de_xml(tmp_path: Path, falsos: Falsos) -> None:
    raiz = tmp_path / "a & <b>"
    raiz.mkdir()
    caixa = _caixa(raiz, falsos)

    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    assert _plist_valido(caixa.plist)
    assert _ler_plist(caixa.plist) == _agente_esperado(caixa, caixa.falsos.uv / "uv")


def test_install_recarrega_agente_mesmo_sem_estar_carregado(caixa: Caixa) -> None:
    # O launchctl falso falha no bootout, como o de verdade quando o agente não está carregado.
    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    dominio = f"gui/{os.getuid()}"
    assert [c for c in caixa.chamadas() if c.startswith("launchctl")] == [
        f"launchctl bootout {dominio}/{ROTULO}",
        f"launchctl bootstrap {dominio} {caixa.plist}",
    ]


def test_install_sincroniza_dependencias_pelo_lock(caixa: Caixa) -> None:
    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    assert f"uv sync --locked --project {REPO}" in caixa.chamadas()


def test_install_sem_uv_instala_pelo_homebrew(tmp_path: Path, falsos: Falsos) -> None:
    caixa = _caixa(tmp_path, falsos, com_uv=False)

    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    assert caixa.chamadas()[:1] == ["brew install uv"]
    assert _ler_plist(caixa.plist) == _agente_esperado(caixa, caixa.instalados / "uv")


def test_install_sem_uv_nem_homebrew_para_e_explica(tmp_path: Path, falsos: Falsos) -> None:
    caixa = _caixa(tmp_path, falsos, com_uv=False, com_brew=False)

    resultado = _instalar(caixa)

    assert resultado.returncode != 0
    assert "https://brew.sh" in resultado.stderr
    assert caixa.chamadas() == []
    assert not caixa.plist.exists()


INICIO_BLOCO = "# >>> sara-antilixo >>>"
FIM_BLOCO = "# <<< sara-antilixo <<<"
ZSHRC_DO_USUARIO = 'export EDITOR=vim\nalias ll="ls -la"\n'


def test_install_idempotente(caixa: Caixa) -> None:
    _ = caixa.zshrc.write_text(ZSHRC_DO_USUARIO)

    primeira = _instalar(caixa)
    assert caixa.plist.is_file()
    plist_1, zshrc_1 = caixa.plist.read_bytes(), caixa.zshrc.read_text()
    segunda = _instalar(caixa)

    assert (primeira.returncode, segunda.returncode) == (0, 0), segunda.stderr
    assert caixa.plist.read_bytes() == plist_1
    assert caixa.zshrc.read_text() == zshrc_1
    assert zshrc_1.count(INICIO_BLOCO) == 1
    assert zshrc_1.count(FIM_BLOCO) == 1
    assert zshrc_1.startswith(ZSHRC_DO_USUARIO)


def test_install_troca_bloco_antigo_no_mesmo_lugar(caixa: Caixa) -> None:
    # Achado F1 da auditoria: heartbeat novo no repositório precisa chegar ao ~/.zshrc instalado.
    depois = "export DEPOIS=1\n"
    _ = caixa.zshrc.write_text(f"{ZSHRC_DO_USUARIO}{INICIO_BLOCO}\nvelho\n{FIM_BLOCO}\n{depois}")

    resultado = _instalar(caixa)

    assert resultado.returncode == 0, resultado.stderr
    heartbeat = (REPO / "instalacao" / "heartbeat.zsh").read_text()
    assert caixa.zshrc.read_text() == (
        f"{ZSHRC_DO_USUARIO}{INICIO_BLOCO}\n{heartbeat.rstrip()}\n{FIM_BLOCO}\n{depois}"
    )


@pytest.mark.parametrize(
    "zshrc",
    [
        f"{INICIO_BLOCO}\nvelho\n{ZSHRC_DO_USUARIO}",
        f"{FIM_BLOCO}\n{ZSHRC_DO_USUARIO}{INICIO_BLOCO}\nvelho\n",
        f"{INICIO_BLOCO}\n{FIM_BLOCO}\n{ZSHRC_DO_USUARIO}{INICIO_BLOCO}\n{FIM_BLOCO}\n",
    ],
    ids=["sem-fim", "fora-de-ordem", "dois-blocos"],
)
def test_install_recusa_marcadores_quebrados_sem_mexer_no_zshrc(caixa: Caixa, zshrc: str) -> None:
    # Trocar o bloco num arquivo assim apagaria linhas do usuário até o fim do arquivo.
    _ = caixa.zshrc.write_text(zshrc)

    resultado = _instalar(caixa)

    assert resultado.returncode != 0
    assert "marcador" in resultado.stderr
    assert caixa.zshrc.read_text() == zshrc


def _abrir_terminal(caixa: Caixa) -> subprocess.CompletedProcess[str]:
    """Um zsh novo lendo o ~/.zshrc instalado, como ao abrir o terminal."""
    return subprocess.run(  # noqa: S603  # motivo: zsh do sistema, caminho absoluto, sem shell
        ["/bin/zsh", "-f", "-c", f"source {caixa.zshrc}"],
        env={"HOME": str(caixa.home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


_HORA = 3600
_DIA = 24 * _HORA


@pytest.mark.parametrize(
    ("idade", "avisa"),
    [(9 * _DIA, True), (8 * _DIA + _HORA, True), (8 * _DIA - _HORA, False), (_DIA, False)],
    ids=["9-dias", "8-dias-e-1-hora", "7-dias-e-23-horas", "1-dia"],
)
def test_heartbeat_avisa_so_com_relatorio_de_mais_de_8_dias(
    caixa: Caixa, idade: int, *, avisa: bool
) -> None:
    assert _instalar(caixa).returncode == 0
    assert caixa.estado.is_dir()
    relatorio = caixa.estado / "relatorio.md"
    _ = relatorio.write_text("# relatório\n")
    quando = time.time() - idade
    os.utime(relatorio, (quando, quando))

    terminal = _abrir_terminal(caixa)

    assert terminal.returncode == 0
    assert terminal.stdout == ""
    assert ("sara-antilixo" in terminal.stderr) is avisa
    if not avisa:
        assert terminal.stderr == ""


@pytest.mark.parametrize("sem_pasta", [False, True], ids=["sem-relatorio", "sem-pasta-de-estado"])
def test_heartbeat_avisa_sem_relatorio_e_nao_quebra_o_shell(
    caixa: Caixa, *, sem_pasta: bool
) -> None:
    assert _instalar(caixa).returncode == 0
    assert caixa.estado.is_dir()
    if sem_pasta:
        shutil.rmtree(caixa.estado)

    terminal = _abrir_terminal(caixa)

    assert terminal.returncode == 0
    assert "sara-antilixo" in terminal.stderr
