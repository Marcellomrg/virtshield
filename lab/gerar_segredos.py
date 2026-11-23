from pathlib import Path
from secrets import token_hex

directory = Path(__file__).resolve().parents[1] / "secrets"
directory.mkdir(mode=0o700, exist_ok=True)

for name in ("db_password", "app_password"):
    path = directory / name
    try:
        with path.open("x", encoding="ascii") as secret_file:
            secret_file.write(token_hex(32) + "\n")
    except FileExistsError:
        continue
    # O diretório privado protege os arquivos no host. Os UIDs dos serviços
    # precisam ler cada arquivo montado individualmente no contêiner.
    path.chmod(0o644)

print("Segredos locais disponíveis. Os arquivos existentes foram preservados.")
