"""A Linux-csomag építése a (Windowsos) forrásból: out/Kepprofil-linux-<verzió>.tar.gz, másolat a Dokumentumok\\telepitok mappába.

    .venv\\Scripts\\python build_linux.py

A csomag ugyanaz a kód, mint a Windowsos változat; kimarad belőle a Windows-réteg (hw_windows, system_windows), a build- és
tesztfájlok. A csomagoló ellenőrzi, hogy minden betett modul lefordul, és semmi nem hivatkozik a csomagból hiányzó modulra."""
import ast
import io
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDE = {"hw_windows.py", "system_windows.py", "make_icon.py", "build_linux.py"}
PLATFORM_ONLY = {"hw_windows", "system_windows"}              # a hw.py / system.py csak win32-n tölti be
DATA_FILES = ["assets/icon.ico", "requirements.txt", "README.md", "LINUX.md"]
SCRIPTS = {"linux/install.sh": "install.sh", "linux/uninstall.sh": "uninstall.sh"}


def version():
    m = re.search(r'^VERSION = "(.+?)"', (ROOT / "consts.py").read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit("Nincs VERSION a consts.py-ban.")
    return m.group(1)


def local_imports(path, modules):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
        found |= {n.split(".")[0] for n in names} & modules
    return found


def main():
    ver = version()
    sources = sorted(p for p in ROOT.glob("*.py") if p.name not in EXCLUDE)
    modules = {p.stem for p in ROOT.glob("*.py")}
    packaged = {p.stem for p in sources}

    problems = []
    for p in sources:
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as e:
            problems.append(f"{p.name}: szintaxishiba: {e}")
        missing = local_imports(p, modules) - packaged - PLATFORM_ONLY
        if missing:
            problems.append(f"{p.name}: a csomagból hiányzó modul: {', '.join(sorted(missing))}")
    for name in DATA_FILES + list(SCRIPTS):
        if not (ROOT / name).is_file():
            problems.append(f"hiányzó fájl: {name}")
    if problems:
        sys.exit("A csomag nem építhető:\n  " + "\n  ".join(problems))

    top = f"kepprofil-{ver}"
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    target = out / f"Kepprofil-linux-{ver}.tar.gz"

    def add(tar, data, arcname, mode):
        info = tarfile.TarInfo(f"{top}/{arcname}")
        info.size, info.mode, info.uname, info.gname = len(data), mode, "", ""
        tar.addfile(info, io.BytesIO(data))

    with tarfile.open(target, "w:gz") as tar:
        for p in sources:
            add(tar, p.read_bytes().replace(b"\r\n", b"\n"), p.name, 0o755 if p.name == "kijelzo.py" else 0o644)
        for name in DATA_FILES:
            data = (ROOT / name).read_bytes()
            add(tar, data if name.endswith(".ico") else data.replace(b"\r\n", b"\n"), name, 0o644)
        for src, dst in SCRIPTS.items():
            add(tar, (ROOT / src).read_bytes().replace(b"\r\n", b"\n"), dst, 0o755)

    docs = Path.home() / "Documents" / "telepitok"
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, docs / target.name)
    print(f"Kész: {target} ({target.stat().st_size} bájt, {len(sources)} modul)")
    print(f"Másolat: {docs / target.name}")


if __name__ == "__main__":
    main()
