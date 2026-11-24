"""Compare os controles simulados e inspecione o VirtShield em execução."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from auditor import CONTROLS, SQL_POLICY

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ("docker", "compose", "-f", str(ROOT / "compose.yaml"))
SECRET_PATH = "/run/secrets/app_password"
REFERENCE = {
    "segredos": "Credencial descrita como exposta na configuração.",
    "rede": "Porta do PostgreSQL descrita como publicada no host.",
    "processo": "Aplicação descrita com privilégios elevados.",
    "banco": "Conta descrita com poderes de alteração no banco.",
    "superficie": "Arquivos graváveis e processo com privilégios amplos.",
}


def run(*arguments, accepted=(0,)):
    result = subprocess.run(
        arguments, cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    if result.returncode not in accepted:
        raise RuntimeError(f"Falha ao consultar {' '.join(arguments[:4])}. Confira docker compose ps.")
    return result.stdout.strip(), result.returncode


def active(service):
    container, _ = run(*COMPOSE, "ps", "-q", service)
    if not container or "\n" in container:
        raise RuntimeError(f"Esperava um contêiner em execução para {service}.")
    return container


def inspect(container, field):
    value, _ = run("docker", "inspect", "--format", "{{json " + field + "}}", container)
    return json.loads(value)


def secret():
    # Inspeciona destinos e testa a legibilidade, sem consultar o conteúdo.
    mounts = inspect(active("app"), ".Mounts") or []
    mounted = any(mount.get("Destination") == SECRET_PATH for mount in mounts)
    _, code = run(
        *COMPOSE, "exec", "-T", "app", "sh", "-c",
        'test "$APP_PASSWORD_FILE" = "/run/secrets/app_password" && test -r "$APP_PASSWORD_FILE"',
        accepted=(0, 1),
    )
    readable = code == 0
    return mounted and readable, [
        f"Segredo montado em {SECRET_PATH}: {yes(mounted)}",
        f"Caminho configurado e arquivo legível para a aplicação: {yes(readable)}",
    ]


def network():
    container = active("db")
    published = bool(inspect(container, ".HostConfig.PortBindings"))
    networks = inspect(container, ".NetworkSettings.Networks") or {}
    internal = {}
    for name in networks:
        result, _ = run("docker", "network", "inspect", "--format", "{{.Internal}}", name)
        internal[name] = result == "true"
    checks = [f"{name}: rede interna = {yes(value)}" for name, value in internal.items()]
    return bool(internal) and all(internal.values()) and not published, [
        *checks, f"PostgreSQL tem porta publicada no host: {yes(published)}",
    ]


def process():
    privileged = inspect(active("app"), ".HostConfig.Privileged")
    uid, _ = run(*COMPOSE, "exec", "-T", "app", "id", "-u")
    return uid.isdecimal() and int(uid) > 0 and privileged is False, [
        f"UID do processo consultado no contêiner: {uid}",
        f"Modo privilegiado: {yes(privileged)}",
    ]


def database():
    user, _ = run(*COMPOSE, "exec", "-T", "app", "printenv", "APP_DB_USER", accepted=(0, 1))
    query = """
        SELECT has_table_privilege('app_user', 'public.labels', 'SELECT'),
               has_table_privilege('app_user', 'public.labels', 'INSERT'),
               has_table_privilege('app_user', 'public.labels', 'UPDATE'),
               has_table_privilege('app_user', 'public.labels', 'DELETE'),
               has_table_privilege('app_user', 'public.labels', 'TRUNCATE')
    """

    def sql(statement):
        result, _ = run(
            *COMPOSE, "exec", "-T", "db", "psql", "-XAt", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", "virtshield", "-c", statement,
        )
        return result

    access = sql(query).split("|")
    policy = sql(SQL_POLICY) == "t"
    return user == "app_user" and policy, [
        f"Conta configurada na aplicação: {user or 'ausente'}",
        *[f"{operation} na tabela public.labels: {yes(value == 't')}"
          for operation, value in zip(("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"), access)],
        f"Demais condições de menor privilégio do auditor: {yes(policy)}",
    ]


def container_security():
    container = active("app")
    readonly = inspect(container, ".HostConfig.ReadonlyRootfs")
    drops = inspect(container, ".HostConfig.CapDrop") or []
    options = inspect(container, ".HostConfig.SecurityOpt") or []
    all_dropped = "ALL" in drops
    locked = any(setting in {"no-new-privileges", "no-new-privileges:true", "no-new-privileges=true"}
                 for setting in options)
    return readonly and all_dropped and locked, [
        f"Sistema de arquivos somente leitura: {yes(readonly)}",
        f"Todas as capacidades removidas: {yes(all_dropped)}",
        f"Bloqueio de novos privilégios: {yes(locked)}",
    ]


def yes(value):
    return "sim" if value else "não"


CHECKS = dict(zip(("segredos", "rede", "processo", "banco", "superficie"),
                  (secret, network, process, database, container_security)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automatico", action="store_true", help="Avança sem esperar Enter.")
    args = parser.parse_args()
    reference = json.loads((ROOT / "lab" / "cenarios.json").read_text(encoding="utf-8"))["referencia"]
    passed = 0
    print("VIRTSHIELD | INSPEÇÃO POR ETAPAS")
    for number, (key, title) in enumerate(CONTROLS, 1):
        print(f"\n[{number}/{len(CONTROLS)}] {title}")
        print(f"  ANTES | Referência simulada | {'ATENDE' if reference[key] else 'FALHA'}")
        print(f"    {REFERENCE[key]}")
        if not args.automatico and sys.stdin.isatty():
            input("  Pressione Enter para verificar o Docker em execução. ")
        ok, details = CHECKS[key]()
        passed += int(ok)
        print(f"  DEPOIS | Docker em execução | {'PASSOU' if ok else 'FALHOU'}")
        for item in details:
            print(f"    {item}")
        print(f"  Pontos confirmados até aqui: {passed * 20}/100")

    print(f"\nRESUMO | Referência: {sum(reference[key] for key, _ in CONTROLS) * 20}/100 | "
          f"Docker em execução: {passed * 20}/100")
    return 0 if passed == len(CONTROLS) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"Inspeção interrompida: {error}")
