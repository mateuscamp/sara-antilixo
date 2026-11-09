"""Limpeza de caches recriáveis. O único lugar do projeto que apaga (ADR-0001)."""

import shutil
from pathlib import Path

from antilixo.dominio.allowlist import CACHES_RECRIAVEIS, esta_na_allowlist


class ForaDaAllowlistError(ValueError):
    """O caminho pedido, resolvido, não fica dentro de nenhum cache da allowlist."""


def limpar(alvo: Path, *, home: Path) -> None:
    """Apaga `alvo` (pasta ou arquivo) se, resolvido, ele ficar dentro de um cache da allowlist.

    Resolve antes de comparar: `..` e symlinks levariam para fora da allowlist um caminho que, em
    texto, parece estar dentro dela. Apaga o caminho resolvido, o mesmo que passou na checagem,
    e não o texto recebido (achado A2 da revisão de 2026-11-08). Resta uma janela entre checar e
    apagar: um ancestral trocado por symlink nesse intervalo seria seguido (achado 4 da revisão
    de 2026-11-09, aceito por exigir processo hostil do próprio usuário).

    Sem exemplo executável aqui de propósito: um doctest desta função apagaria no HOME real se a
    checagem regredisse (achado 1 da revisão de 2026-11-09).
    """
    home_resolvido = home.resolve()
    resolvido = alvo.resolve()
    if not esta_na_allowlist(resolvido, home_resolvido):
        esperado = ", ".join(f"~/{c.as_posix()}" for c in CACHES_RECRIAVEIS)
        msg = f"recusado: {alvo} resolve para {resolvido}; esperado dentro de: {esperado}"
        raise ForaDaAllowlistError(msg)
    _apagar(resolvido)
    _apagar_atalho_se_dentro_da_allowlist(alvo, home_resolvido)


def _apagar(caminho: Path) -> None:
    if caminho.is_dir():
        # rmtree por descritor (avoids_symlink_attacks no macOS e Linux): um symlink plantado
        # dentro do cache durante a remoção é apagado como link, não seguido para fora.
        shutil.rmtree(caminho)
        return
    # A ferramenta dona do cache pode ter apagado antes (achado 2 da revisão de 2026-11-09).
    caminho.unlink(missing_ok=True)


def _apagar_atalho_se_dentro_da_allowlist(alvo: Path, home_resolvido: Path) -> None:
    """Remove o próprio symlink `alvo`, para não deixá-lo pendurado, só se ele morar no cache."""
    if not alvo.is_symlink():
        return
    # Resolve a pasta do atalho, não o atalho: o que se confere é onde o link está, não o destino.
    atalho = alvo.parent.resolve() / alvo.name
    if esta_na_allowlist(atalho, home_resolvido):
        atalho.unlink()
