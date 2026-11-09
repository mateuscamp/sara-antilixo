"""Coletor de caches recriáveis da allowlist (ADR-0001)."""

from pathlib import Path

from antilixo.coletores.caches import coletar_caches
from antilixo.dominio.modelo import Achado, Categoria


def test_cache_presente_vira_achado_com_tamanho_somado(tmp_path: Path) -> None:
    cache = tmp_path / ".cache" / "uv"
    (cache / "sub").mkdir(parents=True)
    _ = (cache / "a.bin").write_bytes(b"x" * 4096 * 3)
    _ = (cache / "sub" / "b.bin").write_bytes(b"y" * 4096 * 2)

    achados = coletar_caches(tmp_path)

    assert achados == (
        Achado(Categoria.CACHE, cache, 4096 * 5, "cache recriável da allowlist: ~/.cache/uv"),
    )


def test_cache_ausente_nao_vira_achado(tmp_path: Path) -> None:
    (tmp_path / ".npm").mkdir()
    _ = (tmp_path / ".gradle").write_bytes(b"arquivo, nao pasta")

    assert coletar_caches(tmp_path) == ()


def test_symlink_dentro_do_cache_nao_conta_o_que_esta_fora(tmp_path: Path) -> None:
    fora = tmp_path / "Documents"
    fora.mkdir()
    _ = (fora / "grande.bin").write_bytes(b"z" * 1000)
    cache = tmp_path / ".npm" / "_cacache"
    cache.mkdir(parents=True)
    _ = (cache / "blob").write_bytes(b"x" * 4096)
    (cache / "atalho-pasta").symlink_to(fora)
    (cache / "atalho-arquivo").symlink_to(fora / "grande.bin")

    achados = coletar_caches(tmp_path)

    assert [a.tamanho_bytes for a in achados] == [4096]


def test_cache_que_e_symlink_para_fora_nao_vira_achado(tmp_path: Path) -> None:
    # limpar() recusaria o alvo resolvido fora da allowlist; medir aqui só gera aviso sem ação.
    fora = tmp_path / "Volumes" / "externo"
    fora.mkdir(parents=True)
    _ = (fora / "blob").write_bytes(b"x" * 50)
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "uv").symlink_to(fora)

    assert coletar_caches(tmp_path) == ()
