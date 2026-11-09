"""Resumo do que um coletor não conseguiu ler, para a seção "Não deu para ler" do relatório.

Buraco de cobertura à vista, e não calado: verificação real de 2026-11-09 sob o launchd.
"""

import errno
from pathlib import Path


def resumir_pastas_nao_lidas(rotulo: str, raiz: Path, erros: list[OSError]) -> tuple[str, ...]:
    """Uma linha por motivo, com a contagem: o log e o relatório não ganham uma linha por pasta.

    EDEADLK é o File Provider recusando baixar uma pasta que está só na nuvem para um processo em
    segundo plano (Dropbox, Proton Drive): nada é baixado, e a pasta fica sem varrer.
    """
    if any(_mesmo_caminho(e, raiz) and _sem_permissao(e) for e in erros):
        return (f"{rotulo}: sem permissão para ler (Privacidade do macOS)",)
    so_na_nuvem = sum(e.errno == errno.EDEADLK for e in erros)
    sem_permissao = sum(_sem_permissao(e) for e in erros)
    outros = len(erros) - so_na_nuvem - sem_permissao
    linhas = [
        (so_na_nuvem, "só na nuvem, não baixadas"),
        (sem_permissao, "sem permissão"),
        (outros, "com erro de leitura"),
    ]
    return tuple(
        f"{rotulo}: {n} {'pasta' if n == 1 else 'pastas'} {motivo}" for n, motivo in linhas if n
    )


def _sem_permissao(erro: OSError) -> bool:
    return erro.errno in {errno.EPERM, errno.EACCES}


def _mesmo_caminho(erro: OSError, raiz: Path) -> bool:
    return caminho_do_erro(erro) == raiz


def caminho_do_erro(erro: OSError) -> Path | None:
    """O caminho que o sistema recusou, quando o erro traz um."""
    # `filename` vem tipado como Any da stdlib: estreita aqui, na borda.
    nome: object = erro.filename  # pyright: ignore[reportAny]  # motivo: atributo da stdlib sem tipo; estreitado na linha seguinte
    return Path(nome) if isinstance(nome, str) else None
