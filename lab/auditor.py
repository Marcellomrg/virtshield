"""Auditoria de metadados de configuração. Nenhum cenário de referência é iniciado."""
import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = (
    ("segredos", "Credencial da aplicação em segredo montado"),
    ("rede", "Banco em rede interna e sem porta publicada"),
    ("processo", "Aplicação sem root e sem modo privilegiado"),
    ("banco", "Conta da aplicação separada e com acesso de leitura"),
    ("superficie", "Sistema de arquivos somente leitura e redução de privilégios"),
)


SQL_POLICY = """
        SELECT NOT r.rolsuper AND NOT r.rolcreatedb AND NOT r.rolcreaterole
           AND c.relowner <> r.oid
           AND NOT pg_has_role(r.oid, c.relowner, 'USAGE')
           AND has_table_privilege(r.oid, c.oid, 'SELECT')
           AND NOT has_table_privilege(r.oid, c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')
           AND NOT has_schema_privilege(r.oid, 'public', 'CREATE')
        FROM pg_roles r
        JOIN pg_class c ON c.oid = 'public.labels'::regclass
        WHERE r.rolname = 'app_user'
    """


def read_implementation():
    config = json.loads(subprocess.check_output(
        ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "config", "--format", "json"],
        cwd=ROOT, timeout=30,
    ))
    app = config["services"]["app"]
    db = config["services"]["db"]
    app_secrets = {item["source"] for item in app.get("secrets", [])}
    environment = app.get("environment", {})
    networks = db.get("networks", {})
    uid = str(app.get("user", "")).split(":")[0]

    sql_result = subprocess.check_output(
        ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "exec", "-T", "db",
         "psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "virtshield",
         "-c", SQL_POLICY],
        cwd=ROOT, timeout=30, text=True,
    ).strip()
    return {
        "segredos": "app_password" in app_secrets
        and environment.get("APP_PASSWORD_FILE") == "/run/secrets/app_password",
        "rede": bool(networks) and not db.get("ports")
        and all(config["networks"][name].get("internal") is True for name in networks),
        "processo": uid.isdigit() and int(uid) > 0 and not app.get("privileged", False),
        "banco": environment.get("APP_DB_USER") == "app_user" and sql_result == "t",
        "superficie": app.get("read_only") is True and "ALL" in app.get("cap_drop", [])
        and any(value in {"no-new-privileges", "no-new-privileges:true", "no-new-privileges=true"}
                for value in app.get("security_opt", [])),
    }


def explain(statuses):
    key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not key:
        return "Gemini desativado. A auditoria de regras foi concluída localmente."
    if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", model):
        return "Modelo Gemini inválido. Confira GEMINI_MODEL."
    summary = ", ".join(f"{name}: {'atende' if passed else 'não atende'}"
                        for (_, name), passed in zip(CONTROLS, statuses))
    prompt = ("Em português, explique em até 100 palavras estes resultados de uma auditoria "
              "didática e recomende medidas defensivas. Não altere a classificação: " + summary)
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 512},
        }).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            parts = json.load(response)["candidates"][0]["content"]["parts"]
        content = " ".join(part["text"] for part in parts if "text" in part and not part.get("thought")).strip()
        if not content:
            raise ValueError("Resposta sem texto")
        return "Gemini · " + content
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return "Explicação do Gemini indisponível. A pontuação de regras foi preservada."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cenario", choices=["referencia", "protegido", "docker"])
    parser.add_argument("--gemini", action="store_true", help="Envia somente os resultados das regras.")
    args = parser.parse_args()
    if args.cenario == "docker":
        try:
            values = read_implementation()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            raise SystemExit("Auditoria Docker indisponível. Valide se o banco está pronto.") from error
        origin = "Compose resolvido e catálogo PostgreSQL do laboratório"
    else:
        data = json.loads((ROOT / "lab" / "cenarios.json").read_text(encoding="utf-8"))
        values = data[args.cenario]
        origin = "Metadados sintéticos · execução do auditor offline"
    statuses = [values[key] for key, _ in CONTROLS]
    score = sum(statuses) * 20
    explanation = explain(statuses) if args.gemini else "Gemini desativado nesta execução."
    table = "".join(f"<tr><td>{escape(name)}</td><td>{'Atende' if passed else 'Não atende'}</td></tr>"
                    for (_, name), passed in zip(CONTROLS, statuses))
    output = ROOT / "evidencias" / f"relatorio_{args.cenario}.html"
    output.parent.mkdir(exist_ok=True)
    output.write_text(f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VirtShield · {args.cenario}</title>
    <style>body{{margin:48px auto;max-width:760px;padding:0 22px;font:18px system-ui;color:#142c38}}
    h1{{color:#087e69}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #c5d8db}}
    table{{border-collapse:collapse;width:100%}}strong{{font-size:36px}}p{{line-height:1.5}}</style>
    <h1>VirtShield · {args.cenario}</h1><p>{escape(origin)}</p>
    <p><strong>{score}/100</strong> · {sum(statuses)} de 5 regras atendidas</p>
    <table><thead><tr><th>Controle</th><th>Resultado</th></tr></thead><tbody>{table}</tbody></table>
    <h2>Explicação</h2><p>{escape(explanation)}</p>
    <p>Escala didática com cinco regras de 20 pontos. Evidência de restauração e varredura de imagens são independentes da nota.</p></html>""",
                      encoding="utf-8")
    print(f"{args.cenario}: {score}/100 ({sum(statuses)} de 5 regras). {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
