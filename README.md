# VirtShield

Laboratório didático de proteção de contêineres com Docker Compose e PostgreSQL.

## Validar no Docker

Com Docker e Python 3.10 ou superior, execute na raiz:

```bash
python lab/validar.py
```

A aplicação fica em http://127.0.0.1:8081. O validador verifica o HTTP, a identidade SQL `app_user`, a configuração do Compose e a restauração dos quatro registros. Os resultados ficam em `evidencias/`. Para parar os serviços, execute `docker compose down`.

## Auditoria offline

```bash
python lab/auditor.py referencia
python lab/auditor.py protegido
```

Os dois perfis usam metadados sintéticos. O perfil protegido também pode ser avaliado em funcionamento com `python lab/auditor.py docker`.

## GitHub Actions

Em **Actions → Validar VirtShield**, o workflow sobe o laboratório, executa o Trivy e guarda as evidências. Para testar o Gemini, configure o secret de repositório `GEMINI_API_KEY` e execute o workflow. A explicação do Gemini complementa a auditoria. A nota é calculada pelas cinco regras em Python.
