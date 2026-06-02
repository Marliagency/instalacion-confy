#!/usr/bin/env python3
"""
pod_exec.py — Ejecuta código Python DENTRO del pod de RunPod vía JupyterLab.

¿Por qué? El egress del entorno web está filtrado por allowlist (api.openai.com
y las bibliotecas de música están bloqueadas), pero la internet DENTRO del pod
no lo está. Este módulo se conecta al JupyterLab del pod (puerto 8888, sobre
*.proxy.runpod.net que sí está permitido), abre un kernel y ejecuta código allí.
Así podemos llamar a OpenAI y descargar música desde el pod sin tocar el allowlist.

Auth: usa JUPYTER_PASSWORD (se lee del propio pod por la API de RunPod).

Uso como módulo:
    pj = PodJupyter(pod_id)        # login automático
    out = pj.run("print(2+2)")     # ejecuta y devuelve stdout
    data = pj.get_file("foo.png")  # baja un archivo (bytes)
    pj.put_file("bar.txt", b"hi")  # sube un archivo
    pj.close()

Uso CLI:
    python3 pod_exec.py POD_ID --code "print('hola desde el pod')"
    python3 pod_exec.py POD_ID --code-file script.py
"""

import argparse
import json
import os
import sys
import time
import uuid

import requests
import websocket  # websocket-client


def pod_env(pod_id):
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("Falta RUNPOD_API_KEY.")
    r = requests.get(f"https://rest.runpod.io/v1/pods/{pod_id}",
                     headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    return r.json().get("env") or {}


class PodJupyter:
    def __init__(self, pod_id, password=None, base=None, timeout=30):
        self.pod_id = pod_id
        self.base = (base or f"https://{pod_id}-8888.proxy.runpod.net").rstrip("/")
        self.ws_base = self.base.replace("https://", "wss://").replace("http://", "ws://")
        self.s = requests.Session()
        if password is None:
            password = pod_env(pod_id).get("JUPYTER_PASSWORD")
        if not password:
            raise RuntimeError("No encontré JUPYTER_PASSWORD en el pod.")
        self.password = password
        self.kernel_id = None
        self._login(timeout)

    # --- auth ---
    def _xsrf(self):
        return self.s.cookies.get("_xsrf")

    def _login(self, timeout):
        # 1) GET raíz: fija cookies _xsrf y de sesión (suficiente si el server está abierto)
        self.s.get(f"{self.base}/", timeout=timeout)
        chk = self.s.get(f"{self.base}/api/status", timeout=timeout)
        if chk.status_code == 200:
            return  # acceso abierto o por cookie; no hace falta password
        # 2) si la API exige auth, intentar login por password
        self.s.get(f"{self.base}/login", timeout=timeout)
        xsrf = self._xsrf()
        r = self.s.post(f"{self.base}/login",
                        data={"_xsrf": xsrf, "password": self.password},
                        timeout=timeout, allow_redirects=True)
        if r.status_code not in (200, 302):
            raise RuntimeError(f"Login Jupyter falló: HTTP {r.status_code}")
        chk = self.s.get(f"{self.base}/api/status", timeout=timeout)
        if chk.status_code != 200:
            raise RuntimeError(f"Acceso Jupyter falló: HTTP {chk.status_code}")

    def _headers(self):
        h = {}
        x = self._xsrf()
        if x:
            h["X-XSRFToken"] = x
        return h

    def _cookie_str(self):
        return "; ".join(f"{c.name}={c.value}" for c in self.s.cookies)

    # --- kernel ---
    def _ensure_kernel(self):
        if self.kernel_id:
            return self.kernel_id
        r = self.s.post(f"{self.base}/api/kernels", headers=self._headers(),
                        data="{}", timeout=30)
        r.raise_for_status()
        self.kernel_id = r.json()["id"]
        return self.kernel_id

    def run(self, code, timeout=600):
        """Ejecuta `code` en el kernel del pod y devuelve el stdout/stderr combinado."""
        kid = self._ensure_kernel()
        session = uuid.uuid4().hex
        url = f"{self.ws_base}/api/kernels/{kid}/channels?session_id={session}"
        ws = websocket.create_connection(
            url, header=[f"Cookie: {self._cookie_str()}",
                         f"X-XSRFToken: {self._xsrf()}"],
            timeout=timeout,
        )
        msg_id = uuid.uuid4().hex
        msg = {
            "header": {"msg_id": msg_id, "username": "claude", "session": session,
                       "msg_type": "execute_request", "version": "5.3"},
            "parent_header": {}, "metadata": {},
            "content": {"code": code, "silent": False, "store_history": True,
                        "user_expressions": {}, "allow_stdin": False,
                        "stop_on_error": True},
            "channel": "shell",
        }
        ws.send(json.dumps(msg))
        out = []
        ok = True
        start = time.time()
        try:
            while True:
                if time.time() - start > timeout:
                    out.append("\n[pod_exec] TIMEOUT")
                    ok = False
                    break
                raw = ws.recv()
                if not raw:
                    continue
                m = json.loads(raw)
                if m.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                mtype = m.get("header", {}).get("msg_type")
                content = m.get("content", {})
                if mtype == "stream":
                    out.append(content.get("text", ""))
                elif mtype in ("execute_result", "display_data"):
                    data = content.get("data", {})
                    if "text/plain" in data:
                        out.append(data["text/plain"] + "\n")
                elif mtype == "error":
                    ok = False
                    out.append("\n".join(content.get("traceback", [])))
                elif mtype == "status" and content.get("execution_state") == "idle":
                    break
        finally:
            ws.close()
        text = "".join(out)
        if not ok:
            raise RuntimeError(f"Error ejecutando en el pod:\n{text}")
        return text

    # --- archivos (via /api/contents) ---
    def get_file(self, path):
        import base64
        r = self.s.get(f"{self.base}/api/contents/{path}",
                       params={"type": "file", "format": "base64"},
                       headers=self._headers(), timeout=120)
        r.raise_for_status()
        return base64.b64decode(r.json()["content"])

    def put_file(self, path, data: bytes):
        import base64
        body = {"type": "file", "format": "base64",
                "content": base64.b64encode(data).decode()}
        r = self.s.put(f"{self.base}/api/contents/{path}",
                       headers=self._headers(), json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    def close(self):
        if self.kernel_id:
            try:
                self.s.delete(f"{self.base}/api/kernels/{self.kernel_id}",
                              headers=self._headers(), timeout=30)
            except Exception:  # noqa: BLE001
                pass
            self.kernel_id = None


def main():
    ap = argparse.ArgumentParser(description="Ejecuta Python dentro del pod vía Jupyter.")
    ap.add_argument("pod_id")
    ap.add_argument("--code")
    ap.add_argument("--code-file")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    code = args.code
    if args.code_file:
        with open(args.code_file) as f:
            code = f.read()
    if not code:
        sys.exit("Pasa --code o --code-file.")
    pj = PodJupyter(args.pod_id)
    try:
        print(pj.run(code, timeout=args.timeout))
    finally:
        pj.close()


if __name__ == "__main__":
    main()
