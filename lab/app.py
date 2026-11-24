from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return

        try:
            with psycopg.connect(
                host=environ.get("APP_DB_HOST", "db"),
                port=int(environ.get("APP_DB_PORT", "5432")),
                dbname="virtshield",
                user=environ["APP_DB_USER"],
                password=Path(environ["APP_PASSWORD_FILE"]).read_text().strip(),
                connect_timeout=3,
            ) as connection:
                user = connection.execute("SELECT current_user").fetchone()[0]
                rows = connection.execute(
                    "SELECT id, label FROM public.labels ORDER BY id"
                ).fetchall()
        except (OSError, psycopg.Error):
            self.send_error(503, "Banco temporariamente indisponível")
            return

        entries = "".join(f"<li>{key} · {escape(label)}</li>" for key, label in rows)
        body = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>VirtShield</title><style>body{{font:20px system-ui;color:#122332;
        margin:10vh auto;max-width:34em;padding:0 24px}}h1{{color:#087c68}}</style>
        <h1>VirtShield</h1><p>PostgreSQL conectado como <strong>{escape(user)}</strong>.</p>
        <h2>Registros de demonstração</h2><ol>{entries}</ol></html>""".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    host = environ.get("APP_HTTP_HOST", "0.0.0.0")
    port = int(environ.get("APP_HTTP_PORT", "8080"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
