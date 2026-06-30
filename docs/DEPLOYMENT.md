# Despliegue local - Nexo v3

Nexo corre **enteramente local**: en la maquina del productor o en un servidor
local de la correduria. No requiere servicios externos ni internet para el camino
de datos. Lo unico que sale de la maquina es, opcionalmente, la llamada a Claude
para redactar prosa (si `NEXO_USE_LLM=1`); con el default `0`, nada sale.

## Requisitos

- Python 3.11+ (probado en 3.14).
- Sin base de datos externa: el store es un archivo **DuckDB** local.
- Sistema operativo: Windows, macOS o Linux.

## Opcion A - maquina del productor (recomendada para 1 seat)

```bash
git clone <repo privado> nexo-os && cd nexo-os
make install                       # Windows: ./make.ps1 install
cp .env.example .env               # completar NEXO_BOOTSTRAP_ADMIN_* (y ANTHROPIC_API_KEY si aplica)
make bootstrap-admin               # crea el admin inicial
make run                           # abre el tablero en http://localhost:8501
```

El store queda en `nexo_os/data/store/nexo.duckdb`. Programar `make backup` (ver
SECURITY.md) y guardar la copia fuera de la maquina.

## Opcion B - servidor local (varios seats en la LAN)

Igual que A, pero exponiendo Streamlit en la red interna:

```bash
.venv/Scripts/python -m streamlit run nexo_os/dashboard/app.py \
    --server.address 0.0.0.0 --server.port 8501
```

- Acceder desde la LAN a `http://<ip-del-servidor>:8501`.
- Mantenerlo **dentro de la red interna** (no exponer a internet). Si hace falta
  acceso remoto, usar una VPN, no un puerto publico.
- Crear un usuario por seat (`admin` / `operador`) - el alta de usuarios la hace un
  admin (la primera vez, via `make bootstrap-admin`).

## Opcion C - Docker local (opcional)

Imagen minima (sin servicios externos):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements-v3.txt && pip install -e .
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "nexo_os/dashboard/app.py", \
     "--server.address", "0.0.0.0"]
```

```bash
docker build -t nexo-os .
docker run -p 8501:8501 \
  -e ANTHROPIC_API_KEY=... -e NEXO_BOOTSTRAP_ADMIN_USER=... \
  -e NEXO_BOOTSTRAP_ADMIN_PASSWORD=... \
  -v "$PWD/nexo_os/data/store:/app/nexo_os/data/store" \
  -v "$PWD/backups:/app/backups" \
  nexo-os
```

Montar `store/` y `backups/` como volumenes para **persistir el sistema de
registro** fuera del contenedor. Correr `make bootstrap-admin` una vez (o dejar que
el primer arranque lo haga si se agrega al CMD).

## Actualizaciones

1. `make backup` (siempre antes de actualizar).
2. `git pull` en la rama de produccion.
3. `make install` (refresca dependencias).
4. `make test && make eval` (deben quedar verdes antes de operar).
5. `make run`.

## Checklist de seguridad operativa

- `.env` nunca se commitea; clave de Anthropic dedicada a Nexo.
- Backups fuera de la maquina y protegidos (contienen PII).
- Acceso al tablero solo en LAN/VPN; sin exposicion publica.
- `make eval` verde antes de cada puesta en produccion.
