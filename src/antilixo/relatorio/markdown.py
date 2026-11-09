"""Relatório semanal em Markdown, para uma pessoa e para o Claude lerem (ADR-0001)."""

import re
from datetime import datetime
from pathlib import Path, PurePath

from antilixo.dominio.modelo import (
    Achado,
    AvisoDeCategoria,
    Categoria,
    ResultadoDaLimpeza,
    Veredito,
)
from antilixo.dominio.tamanho import formatar_tamanho
from antilixo.relatorio.estado_em_disco import escrever_atomico

ROTULOS: dict[Categoria, str] = {
    Categoria.ORFAO_LIBRARY: "Órfãos na Library",
    Categoria.PROJETO_PARADO: "Projetos parados",
    Categoria.GIT_FORA_DE_DEV: "Repositórios git fora de ~/dev",
    Categoria.FOTOS_EM_NUVEM: "Bibliotecas do Fotos na nuvem",
    Categoria.CACHE: "Caches recriáveis",
}


def montar_relatorio(veredito: Veredito, resultado: ResultadoDaLimpeza, agora: datetime) -> str:
    linhas = [f"# Relatório do antilixo — {agora:%Y-%m-%d %H:%M}", ""]
    if veredito.crescimento_do_disco_bytes is not None:
        crescimento = formatar_tamanho(veredito.crescimento_do_disco_bytes)
        linhas.extend(
            ["## Disco", "", f"O uso do disco cresceu {crescimento} nos últimos 30 dias.", ""]
        )
    if not veredito.avisos:
        linhas.extend(["Nada novo: nenhuma categoria passou de 2 GB.", ""])
    for aviso in veredito.avisos:
        linhas.extend(_secao_do_aviso(aviso))
    linhas.extend(
        _secao(
            "Apagado",
            [
                f"{codigo(a.caminho)} — {formatar_tamanho(a.tamanho_bytes)}"
                for a in resultado.apagados
            ],
        )
    )
    linhas.extend(
        _secao(
            "Falhas de limpeza",
            [f"{codigo(f.achado.caminho)} — {em_uma_linha(f.erro)}" for f in resultado.falhas],
        )
    )
    return "\n".join(linhas)


def _secao(titulo: str, itens: list[str]) -> list[str]:
    if not itens:
        return []
    return [f"## {titulo}", "", *(f"- {item}" for item in itens), ""]


def _secao_do_aviso(aviso: AvisoDeCategoria) -> list[str]:
    titulo = f"## {ROTULOS[aviso.categoria]}: {formatar_tamanho(aviso.total_bytes)}"
    maiores_primeiro = sorted(aviso.achados, key=lambda a: a.tamanho_bytes, reverse=True)
    return [titulo, "", *(_linha_do_achado(a) for a in maiores_primeiro), ""]


def _linha_do_achado(achado: Achado) -> str:
    tamanho = formatar_tamanho(achado.tamanho_bytes)
    return f"- {codigo(achado.caminho)} — {tamanho} — {em_uma_linha(achado.motivo)}"


_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
# Quebram linha para quem divide o texto por `splitlines` (U+0085, U+2028, U+2029) ou invertem a
# ordem exibida (controles bidi): um nome assim engana quem lê (achado A3 de 2026-11-09).
_INVISIVEIS = re.compile(r"[\u0085\u2028\u2029\u202a-\u202e\u2066-\u2069]")


def em_uma_linha(texto: str) -> str:
    """Troca caracteres de controle e invisíveis perigosos pela forma escapada (`\\n`, `\\u2028`).

    Nome de pasta e motivo vêm do disco: uma quebra de linha neles criaria título ou item novo
    no relatório que o Claude lê.
    """
    texto = _CONTROLE.sub(lambda m: repr(m.group())[1:-1], texto)
    return _INVISIVEIS.sub(lambda m: f"\\u{ord(m.group()):04x}", texto)


def codigo(caminho: PurePath) -> str:
    """Caminho como código Markdown, com cerca mais longa que qualquer crase do próprio nome."""
    texto = em_uma_linha(str(caminho))
    if "`" not in texto:
        return f"`{texto}`"
    cerca = "`" * (_maior_sequencia_de_crases(texto) + 1)
    return f"{cerca} {texto} {cerca}"


def _maior_sequencia_de_crases(texto: str) -> int:
    maior = atual = 0
    for caractere in texto:
        atual = atual + 1 if caractere == "`" else 0
        maior = max(maior, atual)
    return maior


def gravar_relatorio(texto: str, pasta_de_estado: Path, agora: datetime) -> Path:
    """Grava `relatorio.md` (sempre o último) e a cópia `relatorios/AAAA-MM-DD.md`.

    O heartbeat do `.zshrc` olha a data de `relatorio.md`; por isso a cópia vai primeiro e o
    último só é trocado quando tudo deu certo. Devolve o caminho de `relatorio.md`.
    """
    escrever_atomico(pasta_de_estado / "relatorios" / f"{agora:%Y-%m-%d}.md", texto)
    ultimo = pasta_de_estado / "relatorio.md"
    escrever_atomico(ultimo, texto)
    return ultimo
