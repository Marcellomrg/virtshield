"""Sobe o VirtShield, valida HTTP e SQL e testa a restauração do PostgreSQL."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "compose.yaml")]
URL = "http://127.0.0.1:8081/"


def run(*command, **options):
    return subprocess.run(command, check=True, cwd=ROOT, **options)


def wait_for_app():
    deadline = monotonic() + 45
    while monotonic() < deadline:
        try:
            with urlopen(URL, timeout=3) as response:
                return response.read().decode("utf-8")
        except OSError:
            sleep(1)
    raise SystemExit("A aplicação não respondeu em http://127.0.0.1:8081.")


def main():
    run(*COMPOSE, "version")
    run("docker", "info", "--format", "Docker Engine {{.ServerVersion}}")
    run(sys.executable, "lab/gerar_segredos.py")
    run(*COMPOSE, "config", "--quiet")
    run(*COMPOSE, "up", "-d", "--build", "--wait", "--wait-timeout", "120")
    html = wait_for_app()
    if "<strong>app_user</strong>" not in html or html.count("<li>") != 4:
        raise SystemExit("A aplicação não exibiu app_user e os quatro registros.")
    output = ROOT / "evidencias"
    output.mkdir(exist_ok=True)
    (output / "aplicacao_docker.html").write_text(html, encoding="utf-8")
    audit_command = [sys.executable, "lab/auditor.py", "docker"]
    if os.getenv("GEMINI_API_KEY"):
        audit_command.append("--gemini")
    audit = run(*audit_command, stdout=subprocess.PIPE, text=True)
    print(audit.stdout.strip())
    if not audit.stdout.startswith("docker: 100/100 (5 de 5 regras)."):
        raise SystemExit("O perfil protegido não atende a todos os controles.")
    run(sys.executable, "lab/restaurar.py")
    images = run("docker", "image", "inspect", "--format", "{{.Id}} {{join .RepoDigests \",\"}}",
                 "virtshield-app:local", "postgres:16-alpine",
                 stdout=subprocess.PIPE, text=True).stdout.splitlines()
    ready = {"ambiente": "Docker Compose", "http": 200, "identidade_sql": "app_user",
             "linhas_http": 4, "nota": 100, "identificadores_das_imagens": images,
             "utc": datetime.now(timezone.utc).isoformat()}
    (output / "validacao_docker.json").write_text(json.dumps(ready, indent=2, ensure_ascii=False),
                                                encoding="utf-8")
    print("VirtShield validado no Docker. Evidências em evidencias/.")


if __name__ == "__main__":
    main()
