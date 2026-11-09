"""Tamanho legível, o mesmo no relatório, na notificação e no motivo dos achados."""

GB = 1_000_000_000  # decimal, como o Finder mostra
MB = 1_000_000


def formatar_tamanho(tamanho_bytes: int) -> str:
    """Tamanho legível em unidades decimais, com vírgula: `3,2 GB`, `450 MB`."""
    if tamanho_bytes >= GB:
        return f"{tamanho_bytes / GB:.1f} GB".replace(".", ",")
    return f"{tamanho_bytes // MB} MB"
