"""Gera uma árvore de código ofuscado (PyArmor) para o PyInstaller empacotar.

Saída em <out>/: pacote `eztractor` ofuscado, `launcher.py` ofuscado e o `pyarmor_runtime_*`.
O resto do app (site, fontes, ffmpeg, dependências) é empacotado normalmente pelo .spec.

Uso: python packaging/windows/obfuscate.py <pasta_de_saida>
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "pyarmor.cli", "gen",
        "-O", str(out),
        "--recursive",   # ofusca todos os módulos do pacote
        str(ROOT / "backend" / "eztractor"),
        str(HERE / "launcher.py"),
    ]
    subprocess.run(cmd, check=True)
    assert (out / "eztractor").is_dir() and (out / "launcher.py").exists(), "ofuscação incompleta"
    runtime = next(out.glob("pyarmor_runtime_*"), None)
    assert runtime is not None, "runtime do PyArmor não gerado"
    print(f"ofuscado em {out} (runtime: {runtime.name})")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "obf")
