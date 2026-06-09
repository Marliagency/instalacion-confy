#!/usr/bin/env python3
"""studio_server.py — endpoint HTTP que dispara `studio.py make`.

Pieza que faltaba para que **n8n Cloud** (sin nodo Execute Command) pueda lanzar
la generación: n8n hace `POST /make-video` con el JSON del brief y este servidor
ejecuta `studio_webhook.run_make` (que llama a `studio.py make`). n8n NO reimplementa
nada; sólo dispara. La inteligencia sigue en studio.py + engine/llm.py.

Corre en un host con el repo + claves (ANTHROPIC_API_KEY, RUNPOD_API_KEY, OpenAI,
ElevenLabs). No necesita GPU propia: `studio.py make` enciende/apaga el pod por la
API de RunPod durante el lote. Puede ser un VPS pequeño o un pod CPU barato siempre
encendido.

Uso:
    STUDIO_TOKEN=<secreto> python3 studio_server.py            # escucha en :8099
    STUDIO_TOKEN=<secreto> PORT=9000 python3 studio_server.py

Contrato (idéntico al webhook del repo):
    POST /make-video   header  X-Auth-Token: <STUDIO_TOKEN>
    body  {"slug":"marli","brief":"...","max_cost":3,"approve":false}
    ->  200 {ok:true,  outputs_dir, log, ...}      vídeo listo
        422 {ok:false, exit, log, ...}             PARADA (coste/assets)
        400 {ok:false, error}                      petición inválida
        401 {ok:false, error}                      token ausente/incorrecto

    GET  /health  ->  200 {ok:true}                liveness sin auth

Nota: `make` puede tardar minutos (GPU). La respuesta es **síncrona**: configura un
timeout generoso en el nodo HTTP de n8n (p.ej. 30-60 min) o usa el patrón de PARADA
por coste para aprobar en una segunda llamada.
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from studio_webhook import run_make

TOKEN = os.environ.get("STUDIO_TOKEN", "")
PORT = int(os.environ.get("PORT", "8099"))
MAKE_PATH = os.environ.get("STUDIO_PATH", "/make-video")


class Handler(BaseHTTPRequestHandler):
    server_version = "studio-server/1.0"

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/healthz", ""):
            return self._send(200, {"ok": True, "service": "studio-server"})
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != MAKE_PATH.rstrip("/"):
            return self._send(404, {"ok": False, "error": "not found"})
        if TOKEN and self.headers.get("X-Auth-Token", "") != TOKEN:
            return self._send(401, {"ok": False, "error": "token ausente o incorrecto"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            req = json.loads(raw) if raw else {}
        except Exception as e:
            return self._send(400, {"ok": False, "error": f"JSON inválido: {e}"})

        try:
            result, rc = run_make(req)
        except Exception as e:  # noqa: BLE001 — nunca tumbar el servidor por un lote
            return self._send(500, {"ok": False, "error": f"fallo ejecutando make: {e}"})

        # rc: 0 vídeo OK (200) · 1 PARADA coste/assets (422) · 2 petición inválida (400)
        code = 200 if rc == 0 else (400 if rc == 2 else 422)
        self._send(code, result)

    def log_message(self, fmt, *a):  # log compacto a stderr
        sys.stderr.write("[studio-server] " + (fmt % a) + "\n")


def main():
    if not TOKEN:
        sys.stderr.write(
            "[studio-server] AVISO: STUDIO_TOKEN vacío → endpoint SIN auth. "
            "Define STUDIO_TOKEN para exigir el header X-Auth-Token.\n")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write(f"[studio-server] escuchando en :{PORT}  POST {MAKE_PATH}\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
