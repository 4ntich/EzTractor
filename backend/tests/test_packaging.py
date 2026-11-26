"""A proteção do código no instalador (PyArmor gratuito) recusa arquivos grandes ("out of license").
Um arquivo de 27,7 KB passou e um de 29,5 KB falhou; mantemos todos abaixo de 26 KB com folga."""

from pathlib import Path

LIMIT = 26_000


def test_every_module_fits_the_obfuscator_limit():
    root = Path(__file__).resolve().parents[1] / "eztractor"
    big = {str(p.relative_to(root)): p.stat().st_size for p in root.rglob("*.py") if p.stat().st_size > LIMIT}
    assert not big, f"divida estes arquivos (limite {LIMIT} bytes): {big}"
