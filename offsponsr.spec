# The recipe PyInstaller builds the app by: a folder with offsponsr.exe in dist/offsponsr.
#
# Build the frontend first (`npm run build` in frontend/), then from the repo root:
#     uv run --group build pyinstaller offsponsr.spec --noconfirm

from pathlib import Path

ROOT = Path(SPECPATH)
SOURCES = ROOT / 'src'
PACKAGE = SOURCES / 'offsponsr'
WEB = PACKAGE / 'web'
MIGRATIONS = PACKAGE / 'library' / 'migrations'

if not (WEB / 'index.html').is_file():
    raise SystemExit('The frontend is not built: run `npm run build` in frontend/ first.')


def in_place(path):
    """A file that goes into the build under the same folders the package keeps it in."""
    return str(path), str(path.parent.relative_to(SOURCES))


# Alembic reads the migrations as files, so they travel as data and not as modules.
migrations = [in_place(path) for kind in ('*.py', '*.mako') for path in MIGRATIONS.rglob(kind)]

analysis = Analysis(
    [str(PACKAGE / '__main__.py')],
    pathex=[str(SOURCES)],
    datas=[(str(WEB), 'offsponsr/web'), *migrations],
    # Nothing here draws a window with these; left in, they only add weight.
    excludes=['tkinter', 'unittest', 'pydoc'],
)

archive = PYZ(analysis.pure)

program = EXE(
    archive,
    analysis.scripts,
    exclude_binaries=True,
    name='offsponsr',
    # A window of its own and no console behind it; the log goes to a file.
    console=False,
    upx=False,
)

COLLECT(program, analysis.binaries, analysis.datas, name='offsponsr', upx=False)
