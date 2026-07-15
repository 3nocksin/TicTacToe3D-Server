# Servidor Tic Tac Toe 3D Online

Este repositorio contiene solamente el servidor online del videojuego.
Render ejecuta FastAPI y recibe conexiones WebSocket en `/ws`.

## Comandos de Render

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn server.app:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

El archivo `render.yaml` permite crear el servicio mediante **New > Blueprint**.

## Prueba

Al terminar el despliegue, abre:

- `https://TU-SERVICIO.onrender.com/`
- `https://TU-SERVICIO.onrender.com/health`

El cliente del juego se conecta a:

`wss://TU-SERVICIO.onrender.com/ws`
