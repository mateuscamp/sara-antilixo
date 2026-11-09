"""Notificação do macOS via osascript, só quando há algo novo (driver de silêncio, ADR-0001)."""

import logging
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from antilixo.dominio.modelo import Categoria, ResultadoDaLimpeza, Veredito
from antilixo.relatorio.markdown import formatar_tamanho

logger = logging.getLogger(__name__)

# Caminho absoluto: o LaunchAgent roda com PATH mínimo.
OSASCRIPT = "/usr/bin/osascript"

FRASES: dict[Categoria, str] = {
    Categoria.ORFAO_LIBRARY: "de órfãos na Library",
    Categoria.PROJETO_PARADO: "em projetos parados",
    Categoria.GIT_FORA_DE_DEV: "em repositórios git fora de ~/dev",
    Categoria.FOTOS_EM_NUVEM: "em bibliotecas do Fotos na nuvem",
    Categoria.CACHE: "em caches recriáveis",
}


class ExecutorDeComando(Protocol):
    """Roda um comando sem shell. Devolve se ele terminou com sucesso."""

    def executar(self, argumentos: Sequence[str]) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExecutorDeSubprocesso:
    """Executor real: lista de argumentos, sem shell, com timeout. Nunca levanta."""

    timeout_s: float = 10.0

    def executar(self, argumentos: Sequence[str]) -> bool:
        try:
            concluido = subprocess.run(  # noqa: S603  # motivo: lista de argumentos, sem shell; o texto vai escapado como literal AppleScript
                list(argumentos), capture_output=True, timeout=self.timeout_s, check=False
            )
        except subprocess.TimeoutExpired:
            logger.warning("comando passou de %s s: %s", self.timeout_s, argumentos[0])
            return False
        except OSError as erro:
            logger.warning("comando não rodou: %s (%s)", argumentos[0], erro)
            return False
        if concluido.returncode != 0:
            logger.warning(
                "comando saiu com %s: %s",
                concluido.returncode,
                concluido.stderr.decode(errors="replace"),
            )
            return False
        return True


def notificar(
    veredito: Veredito, resultado: ResultadoDaLimpeza, executor: ExecutorDeComando
) -> bool:
    """Mostra uma notificação se há aviso a notificar, crescimento do disco ou falha de limpeza;
    senão não chama nada e devolve False."""
    partes = [
        f"{formatar_tamanho(a.total_bytes)} {FRASES[a.categoria]}"
        for a in veredito.avisos
        if a.notificar
    ]
    if veredito.crescimento_do_disco_bytes is not None:
        crescimento = formatar_tamanho(veredito.crescimento_do_disco_bytes)
        partes.append(f"disco cresceu {crescimento} em 30 dias")
    if len(resultado.falhas) == 1:
        partes.append(f"falha ao limpar {resultado.falhas[0].achado.caminho.name}")
    elif resultado.falhas:
        partes.append(f"{len(resultado.falhas)} falhas de limpeza")
    if not partes:
        return False
    texto = literal_applescript("; ".join(partes))
    script = f'display notification {texto} with title "antilixo"'
    return executor.executar([OSASCRIPT, "-e", script])


def literal_applescript(texto: str) -> str:
    """Texto entre aspas para o AppleScript. Nomes de pasta entram aqui: sem o escape, uma aspa
    no nome fecharia o literal e o resto viraria comando (`do shell script`)."""
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'
