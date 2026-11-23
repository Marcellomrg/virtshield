"""Restaura um backup laboratorial em um banco temporário e compara as linhas."""
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "exec", "-T", "db"]
QUERY = "SELECT id, label FROM public.labels ORDER BY id"


def run(*command, data=None):
    return subprocess.run(
        [*COMPOSE, *command],
        cwd=ROOT,
        input=data,
        stdout=subprocess.PIPE,
        check=True,
        timeout=60,
    ).stdout


def rows(command, database):
    return command("psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
               "-d", database, "-c", QUERY)


def verify_restore(command, output, ambiente):
    backups = output / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    name = "vs_restore_" + uuid4().hex
    original_rows = rows(command, "virtshield")
    archive = command("pg_dump", "-Fc", "-U", "postgres", "-d", "virtshield")
    (backups / f"{name}.dump").write_bytes(archive)
    start = time.monotonic()
    command("createdb", "-U", "postgres", "-T", "template0", name)
    try:
        command("pg_restore", "--exit-on-error", "-U", "postgres", "-d", name, data=archive)
        restored_rows = rows(command, name)
        elapsed = round(time.monotonic() - start, 3)
        if restored_rows != original_rows or len(restored_rows.splitlines()) != 4:
            raise SystemExit("Falha na verificação dos quatro registros.")
        result = {"registros": 4, "segundos": elapsed, "ambiente": ambiente,
                  "utc": datetime.now(timezone.utc).isoformat(),
                  "arquivo": f"backups/{name}.dump"}
        (output / "restauracao.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        command("dropdb", "-U", "postgres", name)


if __name__ == "__main__":
    result = verify_restore(run, ROOT / "evidencias", "Docker Compose")
    print(f"Restauração OK: 4 de 4 registros em {result['segundos']:.3f} s.")
