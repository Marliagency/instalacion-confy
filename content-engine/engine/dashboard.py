#!/usr/bin/env python3
"""
dashboard.py — Tablero web del Content Engine (sin dependencias).

Sirve una página con el estado de cada semana: conteo por estado, barra de
progreso, tabla de piezas y, si existe, el calendario orgánico. Se refresca solo
cada pocos segundos. Lee directamente los manifest.json (no toca nada).

Uso:
    python3 engine/dashboard.py            # http://localhost:8800
    python3 engine/dashboard.py --port 9000
"""

import argparse
import csv
import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import SEMANAS_DIR, load_manifest, paths_semana

ESTADO_COLOR = {
    "final": "#2e933c", "generado": "#2f6db5", "prompt": "#b58a2f",
    "plan": "#777", "error": "#c0392b",
}


def _semanas():
    if not os.path.isdir(SEMANAS_DIR):
        return []
    return sorted(d for d in os.listdir(SEMANAS_DIR)
                  if os.path.isdir(os.path.join(SEMANAS_DIR, d)))


def _barra(conteo, total):
    if not total:
        return '<div class="bar"></div>'
    seg = []
    for estado in ("final", "generado", "prompt", "plan", "error"):
        n = conteo.get(estado, 0)
        if n:
            pct = 100.0 * n / total
            seg.append(f'<span style="width:{pct:.1f}%;background:{ESTADO_COLOR[estado]}" '
                       f'title="{estado}: {n}"></span>')
    return '<div class="bar">' + "".join(seg) + "</div>"


def _tabla_piezas(piezas):
    filas = []
    for pz in piezas:
        color = ESTADO_COLOR.get(pz["estado"], "#777")
        salidas = ", ".join(sorted(pz.get("salidas", {}).keys())) or "—"
        err = html.escape(pz.get("error") or "")
        filas.append(
            f"<tr>"
            f"<td>{html.escape(pz['id'])}</td>"
            f"<td>{html.escape(pz.get('template',''))}</td>"
            f"<td>{html.escape(pz.get('pilar') or '')}</td>"
            f"<td>{html.escape(pz.get('titular') or '')}</td>"
            f'<td><b style="color:{color}">{pz["estado"]}</b></td>'
            f"<td>{salidas}</td>"
            f'<td class="err">{err}</td>'
            f"</tr>"
        )
    return "".join(filas)


def _tabla_calendario(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        filas = list(csv.reader(f))
    if not filas:
        return ""
    cab, cuerpo = filas[0], filas[1:]
    th = "".join(f"<th>{html.escape(c)}</th>" for c in cab)
    tr = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in fila) + "</tr>"
                 for fila in cuerpo)
    return f"<h3>Calendario</h3><table><tr>{th}</tr>{tr}</table>"


def _render():
    secciones = []
    for semana in _semanas():
        manifest = load_manifest(semana)
        piezas = manifest.get("piezas", [])
        if not piezas:
            continue
        conteo = {}
        for pz in piezas:
            conteo[pz["estado"]] = conteo.get(pz["estado"], 0) + 1
        total = len(piezas)
        finales = sum(len(pz.get("salidas", {})) for pz in piezas if pz["estado"] == "final")
        resumen = " · ".join(f'<span style="color:{ESTADO_COLOR[e]}">{e}: {conteo[e]}</span>'
                             for e in ("final", "generado", "prompt", "plan", "error")
                             if conteo.get(e))
        secciones.append(
            f"<section><h2>{html.escape(semana)} "
            f'<small>({total} piezas · {finales} vídeos)</small></h2>'
            f"<p>{resumen}</p>"
            f"{_barra(conteo, total)}"
            f"<table><tr><th>id</th><th>plantilla</th><th>pilar</th><th>titular</th>"
            f"<th>estado</th><th>formatos</th><th>error</th></tr>"
            f"{_tabla_piezas(piezas)}</table>"
            f"{_tabla_calendario(paths_semana(semana)['calendario'])}"
            f"</section>"
        )
    cuerpo = "".join(secciones) or "<p>No hay semanas con piezas todavía.</p>"
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Content Engine</title>
<style>
 body{{font-family:system-ui,Arial,sans-serif;margin:24px;background:#0f1419;color:#e7e9ea}}
 h1{{margin-top:0}} section{{margin-bottom:40px}}
 small{{color:#888;font-weight:normal}}
 table{{border-collapse:collapse;width:100%;margin-top:8px;font-size:14px}}
 th,td{{border:1px solid #2a2f36;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#1a2027}} .err{{color:#e08a8a;max-width:300px}}
 .bar{{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#2a2f36}}
 .bar span{{display:block;height:100%}}
</style></head><body>
<h1>🎬 Content Engine</h1>
<p style="color:#888">Se refresca solo cada 5 s.</p>
{cuerpo}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = _render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silencia el log de acceso
        pass


def main():
    ap = argparse.ArgumentParser(description="Tablero web del Content Engine.")
    ap.add_argument("--port", type=int, default=8800)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Tablero en http://localhost:{args.port}  (Ctrl-C para salir)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
