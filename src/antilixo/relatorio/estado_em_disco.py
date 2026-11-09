"""Persistência do estado entre execuções semanais."""

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from antilixo.dominio.modelo import AvisoAnterior, Categoria, Estado, MedicaoDeDisco

logger = logging.getLogger(__name__)


class EstadoInvalidoError(ValueError):
    """O conteúdo recebido não corresponde ao formato persistido."""


def _invalido(valor: object, esperado: str) -> EstadoInvalidoError:
    return EstadoInvalidoError(f"Recebido {valor!r}; esperado {esperado}.")


@dataclass(frozen=True, slots=True)
class _ObjetoJson:
    valor: object

    def campo(self, nome: str) -> object:
        if not isinstance(self.valor, dict):
            raise _invalido(self.valor, "objeto JSON")
        campos = cast(dict[str, object], self.valor)  # motivo: JSON só admite chaves string.
        if nome not in campos:
            raise _invalido(campos, f"objeto com a chave {nome!r}")
        return campos[nome]


def _lista(valor: object) -> tuple[object, ...]:
    if not isinstance(valor, list):
        raise _invalido(valor, "lista JSON")
    return tuple(cast(list[object], valor))  # motivo: isinstance valida lista; itens são object.


def _inteiro(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise _invalido(valor, "inteiro não negativo, sem booleanos")
    return valor


def _data(valor: object) -> date:
    if not isinstance(valor, str):
        raise _invalido(valor, "data ISO AAAA-MM-DD")
    try:
        dia = date.fromisoformat(valor)
    except ValueError as erro:
        raise _invalido(valor, "data ISO AAAA-MM-DD") from erro
    if dia.isoformat() != valor:
        raise _invalido(valor, "data ISO AAAA-MM-DD")
    return dia


def _categoria(valor: object) -> Categoria:
    esperado = f"categoria em {tuple(categoria.value for categoria in Categoria)!r}"
    if not isinstance(valor, str):
        raise _invalido(valor, esperado)
    try:
        return Categoria(valor)
    except ValueError as erro:
        raise _invalido(valor, esperado) from erro


def _aviso(valor: object) -> AvisoAnterior:
    objeto = _ObjetoJson(valor)
    return AvisoAnterior(
        _categoria(objeto.campo("categoria")), _inteiro(objeto.campo("total_bytes_no_aviso"))
    )


def _medicao(valor: object) -> MedicaoDeDisco:
    objeto = _ObjetoJson(valor)
    return MedicaoDeDisco(_data(objeto.campo("dia")), _inteiro(objeto.campo("usado_bytes")))


def _estado(valor: object) -> Estado:
    objeto = _ObjetoJson(valor)
    versao = _inteiro(objeto.campo("versao"))
    if versao != 1:
        raise _invalido(versao, "versao igual a 1")
    ultima_limpeza = objeto.campo("ultima_limpeza")
    return Estado(
        avisos_anteriores=tuple(_aviso(item) for item in _lista(objeto.campo("avisos_anteriores"))),
        ultima_limpeza=None if ultima_limpeza is None else _data(ultima_limpeza),
        medicoes=tuple(_medicao(item) for item in _lista(objeto.campo("medicoes"))),
    )


def escrever_atomico(destino: Path, texto: str) -> None:
    """Publica o texto só depois de sincronizar o temporário fixo ao lado."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".tmp")
    # O_NOFOLLOW: um symlink plantado no nome fixo faz a escrita falhar em vez de sobrescrever
    # o alvo dele (achado A1 da auditoria de 2026-11-09). Nome fixo, e não único com O_EXCL,
    # porque relatorio/ não apaga: um temporário de falha anterior é reaproveitado aqui.
    descritor = os.open(
        temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
        _ = arquivo.write(texto)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    _ = temporario.replace(destino)
    # Sem o fsync da pasta, uma queda de energia logo depois pode desfazer a troca de nome
    # (achado A4 da auditoria de 2026-11-09).
    pasta = os.open(destino.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(pasta)
    finally:
        os.close(pasta)


def ler_estado(pasta_de_estado: Path, *, hoje: date) -> Estado:
    """Lê o estado e preserva conteúdo corrompido para inspeção posterior."""
    destino = pasta_de_estado / "estado.json"
    try:
        try:
            texto = destino.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Estado()
        except OSError as erro:
            # Ilegível não é corrompido: nada a preservar renomeando, e a semana não pode
            # travar (achado A2 da auditoria de 2026-11-09). Fica para a pessoa olhar.
            logger.warning("Estado ilegível em %s, seguindo com estado vazio: %s", destino, erro)
            return Estado()
        dados = cast(object, json.loads(texto))  # motivo: isola Any antes da validação estrutural.
        return _estado(dados)
    # ValueError cobre EstadoInvalidoError, JSONDecodeError, UnicodeDecodeError e o limite de
    # dígitos do int; RecursionError vem de aninhamento profundo. Nenhum pode travar a semana.
    except (ValueError, RecursionError) as erro:
        nome_base = f"{destino.name}.corrompido-{hoje:%Y%m%d}"
        corrompido = destino.with_name(nome_base)
        numero = 2
        while corrompido.exists() or corrompido.is_symlink():
            corrompido = destino.with_name(f"{nome_base}-{numero}")
            numero += 1
        _ = destino.rename(corrompido)
        logger.warning("Estado corrompido preservado em %s: %s", corrompido, erro)
        return Estado()


def gravar_estado(pasta_de_estado: Path, estado: Estado) -> None:
    """Grava o formato versionado sem expor um JSON parcial ao leitor."""
    dados = {
        "versao": 1,
        "avisos_anteriores": [
            {
                "categoria": aviso.categoria.value,
                "total_bytes_no_aviso": aviso.total_bytes_no_aviso,
            }
            for aviso in estado.avisos_anteriores
        ],
        "ultima_limpeza": estado.ultima_limpeza.isoformat() if estado.ultima_limpeza else None,
        "medicoes": [
            {"dia": medicao.dia.isoformat(), "usado_bytes": medicao.usado_bytes}
            for medicao in estado.medicoes
        ],
    }
    escrever_atomico(
        pasta_de_estado / "estado.json", json.dumps(dados, indent=2, ensure_ascii=False) + "\n"
    )
