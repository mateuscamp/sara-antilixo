"""Limpeza de caches recriáveis. O único lugar do projeto que apaga (ADR-0001)."""

from pathlib import Path

from antilixo.dominio.allowlist import CACHES_RECRIAVEIS, esta_na_allowlist


class ForaDaAllowlistError(ValueError):
    """O caminho pedido, resolvido, não fica dentro de nenhum cache da allowlist."""


def limpar(alvo: Path, *, home: Path) -> None:
    """Recusa `alvo` fora da allowlist. AINDA NÃO APAGA: a deleção entra com o próximo teste.

    Resolve antes de comparar: `..` e symlinks levariam para fora da allowlist um caminho que, em
    texto, parece estar dentro dela.

    >>> limpar(Path.home() / "Documents", home=Path.home())
    Traceback (most recent call last):
    antilixo.acoes.limpar.ForaDaAllowlistError: ...
    """
    resolvido = alvo.resolve()
    if not esta_na_allowlist(resolvido, home.resolve()):
        esperado = ", ".join(f"~/{c.as_posix()}" for c in CACHES_RECRIAVEIS)
        msg = f"recusado: {alvo} resolve para {resolvido}; esperado dentro de: {esperado}"
        raise ForaDaAllowlistError(msg)
    # A deleção em si entra com o próximo teste (apagar o que está dentro da allowlist).
