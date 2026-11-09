"""Execução semanal ponta a ponta num HOME falso (ADR-0001)."""

import dataclasses
import logging
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from antilixo.coletores.caches import coletar_caches
from antilixo.dominio.modelo import Categoria, Leitura
from antilixo.execucao import Ambiente, coletar_tudo, executar
from antilixo.relatorio.estado_em_disco import ler_estado

AGORA = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


@dataclass
class ExecutorFalso:
    """Guarda os comandos em vez de rodar o osascript."""

    chamadas: list[list[str]] = field(default_factory=list)

    def executar(self, argumentos: Sequence[str]) -> bool:
        self.chamadas.append(list(argumentos))
        return True


def _ambiente(home: Path, executor: ExecutorFalso, agora: datetime = AGORA) -> Ambiente:
    return Ambiente(
        home=home, agora=agora, pastas_de_apps=(home / "Applications",), executor=executor
    )


def _estado(home: Path) -> Path:
    return home / ".local" / "state" / "sara-antilixo"


def _cache_npm(home: Path) -> Path:
    cache = home / ".npm" / "_cacache"
    cache.mkdir(parents=True)
    _ = (cache / "blob").write_bytes(b"x" * 4096)
    return cache


def test_primeira_execucao_apaga_cache_grava_relatorio_e_estado(tmp_path: Path) -> None:
    cache = _cache_npm(tmp_path)

    executar(_ambiente(tmp_path, ExecutorFalso()))

    assert not cache.exists()
    assert (_estado(tmp_path) / "relatorio.md").is_file()
    assert ler_estado(_estado(tmp_path), hoje=AGORA.date()).ultima_limpeza == AGORA.date()


def test_limpeza_que_falhou_em_tudo_nao_avanca_a_ultima_limpeza(tmp_path: Path) -> None:
    # Decidido em 2026-11-09: sem nada apagado, tenta de novo na semana seguinte.
    cache = _cache_npm(tmp_path)
    cache.parent.chmod(0o500)  # ~/.npm sem escrita: rmtree do _cacache falha
    try:
        executar(_ambiente(tmp_path, ExecutorFalso()))
    finally:
        cache.parent.chmod(0o700)

    relatorio = _estado(tmp_path) / "relatorio.md"
    assert relatorio.is_file()
    assert "falha" in relatorio.read_text().lower()
    assert cache.exists()
    assert ler_estado(_estado(tmp_path), hoje=AGORA.date()).ultima_limpeza is None


def test_semana_sem_achado_novo_nao_notifica(tmp_path: Path) -> None:
    executor = ExecutorFalso()

    executar(_ambiente(tmp_path, executor))

    assert executor.chamadas == []


def test_python_m_antilixo_roda_num_home_vazio(tmp_path: Path) -> None:
    # O comando que o LaunchAgent roda. HOME falso: nunca toca o HOME real.
    ambiente = {**os.environ, "HOME": str(tmp_path)}  # noqa: TID251  # motivo: repassa o ambiente ao subprocesso trocando só o HOME
    concluido = subprocess.run(
        [sys.executable, "-m", "antilixo"],
        env=ambiente,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert concluido.returncode == 0, concluido.stderr.decode()
    assert (_estado(tmp_path) / "relatorio.md").is_file()


def test_coleta_inclui_repositorio_git_fora_de_dev(tmp_path: Path) -> None:
    repo = tmp_path / "Documents" / "projeto"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)  # noqa: S603, S607  # motivo: git do PATH com lista fixa, só para montar o repo de teste

    achados = coletar_tudo(_ambiente(tmp_path, ExecutorFalso())).achados

    assert [
        (a.categoria, a.caminho) for a in achados if a.categoria is Categoria.GIT_FORA_DE_DEV
    ] == [(Categoria.GIT_FORA_DE_DEV, repo)]


def test_relatorio_que_nao_grava_nao_impede_estado_nem_limpeza(tmp_path: Path) -> None:
    # Achado da revisão de 2026-11-09: sem isso, a data da limpeza se perdia e a semana seguinte
    # apagava de novo.
    cache = _cache_npm(tmp_path)
    _estado(tmp_path).mkdir(parents=True)
    _ = (_estado(tmp_path) / "relatorios").write_text("arquivo no lugar da pasta")

    executar(_ambiente(tmp_path, ExecutorFalso()))

    assert not cache.exists()
    assert ler_estado(_estado(tmp_path), hoje=AGORA.date()).ultima_limpeza == AGORA.date()


def _coletor_quebrado(ambiente: Ambiente) -> Leitura:
    del ambiente
    msg = "plist esquisito"
    raise ValueError(msg)


def _coletor_de_caches(ambiente: Ambiente) -> Leitura:
    return Leitura(coletar_caches(ambiente.home))


def test_coletor_que_quebra_vira_linha_no_relatorio_e_os_outros_seguem(tmp_path: Path) -> None:
    cache = _cache_npm(tmp_path)
    ambiente = dataclasses.replace(
        _ambiente(tmp_path, ExecutorFalso()),
        coletores=(("quebrado", _coletor_quebrado), ("caches", _coletor_de_caches)),
    )

    executar(ambiente)

    relatorio = _estado(tmp_path) / "relatorio.md"
    assert relatorio.is_file()
    assert "quebrado" in relatorio.read_text()
    assert "plist esquisito" in relatorio.read_text()
    assert not cache.exists()


def test_log_diz_quantos_achados_cada_coletor_trouxe(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Sem isso, uma pasta lida e vazia e uma pasta que o macOS bloqueou davam o mesmo log
    # (verificação real de 2026-11-09).
    caplog.set_level(logging.INFO)
    _ = _cache_npm(tmp_path)
    ambiente = dataclasses.replace(
        _ambiente(tmp_path, ExecutorFalso()), coletores=(("caches", _coletor_de_caches),)
    )

    executar(ambiente)

    assert "coletor caches: 1 achado(s)" in caplog.text


def _coletor_com_buraco(ambiente: Ambiente) -> Leitura:
    del ambiente
    return Leitura(
        (), ("CloudStorage/GoogleDrive-eu: sem permissão para ler (Privacidade do macOS)",)
    )


def test_o_que_nao_deu_para_ler_aparece_no_relatorio(tmp_path: Path) -> None:
    ambiente = dataclasses.replace(
        _ambiente(tmp_path, ExecutorFalso()), coletores=(("fotos-em-nuvem", _coletor_com_buraco),)
    )

    executar(ambiente)

    texto = (_estado(tmp_path) / "relatorio.md").read_text()
    assert "## Não deu para ler" in texto
    assert "GoogleDrive-eu: sem permissão para ler" in texto
