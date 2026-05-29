#!/usr/bin/env python3
"""
jupyter_exec.py — Ejecuta comandos shell en el pod a través de la API de Jupyter.

Útil para diagnosticar/arrancar ComfyUI o inspeccionar los modelos del pod sin
terminal interactiva, cuando ComfyUI (8188) no responde pero Jupyter (8888) sí.

Uso:
    python3 jupyter_exec.py POD_ID "comando shell"
"""
import json
import sys
import uuid
import time
import requests
import websocket

PASSWORD = "ylec50v297dwliey2r1s"


def base_url(pod_id):
    return f"https://{pod_id}-8888.proxy.runpod.net"


def login(base):
    s = requests.Session()
    s.get(f"{base}/login", timeout=30)
    xsrf = s.cookies.get("_xsrf")
    s.post(f"{base}/login", data={"_xsrf": xsrf, "password": PASSWORD},
           timeout=30, allow_redirects=True)
    return s, xsrf


def start_kernel(s, xsrf, base):
    r = s.post(f"{base}/api/kernels", headers={"X-XSRFToken": xsrf},
               data="{}", timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def run(pod_id, cmd, timeout=180):
    base = base_url(pod_id)
    s, xsrf = login(base)
    kid = start_kernel(s, xsrf, base)
    ws_url = base.replace("https://", "wss://") + f"/api/kernels/{kid}/channels"
    cookie = "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items())
    ws = websocket.create_connection(ws_url, timeout=60,
                                     header=[f"Cookie: {cookie}"], cookie=cookie)
    msg_id = uuid.uuid4().hex
    code = (
        "import subprocess\n"
        f"r = subprocess.run({cmd!r}, shell=True, capture_output=True, text=True, timeout={timeout})\n"
        "print(r.stdout)\n"
        "print(r.stderr)\n"
    )
    hdr = {"msg_id": msg_id, "username": "u", "session": uuid.uuid4().hex,
           "msg_type": "execute_request", "version": "5.3"}
    req = {"header": hdr, "parent_header": {}, "metadata": {},
           "content": {"code": code, "silent": False, "store_history": False,
                       "user_expressions": {}, "allow_stdin": False},
           "channel": "shell"}
    ws.send(json.dumps(req))
    out = []
    t0 = time.time()
    while time.time() - t0 < timeout + 30:
        try:
            ws.settimeout(timeout + 30)
            m = json.loads(ws.recv())
        except Exception as e:
            out.append(f"[ws recv error: {e}]")
            break
        if m.get("parent_header", {}).get("msg_id") != msg_id:
            continue
        mt = m.get("msg_type") or m.get("header", {}).get("msg_type")
        c = m.get("content", {})
        if mt == "stream":
            out.append(c.get("text", ""))
        elif mt == "error":
            out.append("\n".join(c.get("traceback", [])))
        elif mt == "execute_reply":
            break
    ws.close()
    try:
        s.delete(f"{base}/api/kernels/{kid}", headers={"X-XSRFToken": xsrf}, timeout=15)
    except Exception:
        pass
    return "".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("uso: jupyter_exec.py POD_ID 'comando'")
    print(run(sys.argv[1], sys.argv[2]))
