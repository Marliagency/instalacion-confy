#!/usr/bin/env python3
"""
edit.py — Convierte los frames de cada pieza en vídeos con ffmpeg.

Para cada pieza en estado 'generado' construye, por cada formato pedido, un
vídeo: cada frame se anima (zoom/pan tipo Ken Burns), se encadenan con
transiciones (xfade), se superpone el titular (drawtext con fuente DejaVu) y, si
hay audio para la pieza, se mezcla. La edición corre en paralelo (config.editores
procesos ffmpeg simultáneos).

Salida:  semanas/<W>/edited/<formato>/<id>.mp4

Uso:
    python3 engine/edit.py 2026-W23
"""

import argparse
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import (
    log, warn, find_font,
    load_manifest, save_manifest, paths_semana, formato_dims,
)

_AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".aac", ".ogg")


def _formato_safe(formato):
    return formato.replace(":", "x")


def _buscar_audio(pieza, audio_dir):
    """Audio explícito de la pieza, o inputs/audio/<id>.<ext> si existe."""
    if pieza.get("audio") and os.path.exists(pieza["audio"]):
        return pieza["audio"]
    for ext in _AUDIO_EXTS:
        cand = os.path.join(audio_dir, f"{pieza['id']}{ext}")
        if os.path.exists(cand):
            return cand
    return None


def _filtro_toma(i, w, h, dur, fps):
    """Filtro Ken Burns para una toma. Alterna zoom-in / zoom-out por variedad."""
    nframes = max(1, int(round(dur * fps)))
    # Recorta al formato y prescala x2: suficiente para que el zoompan no tiemble
    # sin disparar el coste de CPU (x4 multiplicaba por ~4 el tiempo de edición).
    pre = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
           f"scale={2 * w}:{2 * h}")
    if i % 2 == 0:
        z = "min(zoom+0.0012,1.20)"          # zoom-in
    else:
        z = "max(1.2-0.0012*on,1.0)"          # zoom-out (sin estado, arranca en 1.2)
    zp = (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"d={nframes}:s={w}x{h}:fps={fps}")
    return f"[{i}:v]{pre},{zp},setsar=1,format=yuv420p[c{i}]"


def _cadena_xfade(n, dur, fps, transicion):
    """Encadena [c0..cN] con xfade. Devuelve (lineas_filtro, etiqueta_salida)."""
    if n == 1:
        return [], "[c0]"
    lineas = []
    prev = "[c0]"
    acc = dur  # longitud acumulada del encadenado
    for i in range(1, n):
        offset = max(0.0, acc - transicion)
        out = f"[x{i}]"
        lineas.append(
            f"{prev}[c{i}]xfade=transition=fade:duration={transicion}:"
            f"offset={offset:.3f}{out}"
        )
        acc = acc + dur - transicion
        prev = out
    return lineas, prev


def _construir_cmd(pieza, formato, frames, cfg, audio, font, tmp_txt):
    w, h = formato_dims(formato)
    fps = int(cfg.get("fps", 30))
    dur = float(cfg.get("duracion_toma", 3.5))
    transicion = float(cfg.get("transicion", 0.5))
    safe = _formato_safe(formato)
    out_dir = os.path.join(paths_semana(pieza["_semana"])["edited"], safe)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, f"{pieza['id']}.mp4")

    # Una sola imagen por input: zoompan (con d=nframes) genera la duración.
    # Importante: NO usar "-loop 1 -t dur", porque zoompan emite d frames por CADA
    # frame de entrada y un input en bucle dispararía la duración a minutos.
    cmd = ["ffmpeg", "-y"]
    for fr in frames:
        cmd += ["-i", fr]
    if audio:
        cmd += ["-i", audio]

    filtros = [_filtro_toma(i, w, h, dur, fps) for i in range(len(frames))]
    cadena, label = _cadena_xfade(len(frames), dur, fps, transicion)
    filtros += cadena

    # Titular (y CTA opcional) por encima del vídeo.
    cur = label
    if font and (pieza.get("titular") or pieza.get("cta")):
        draws = []
        if pieza.get("titular"):
            draws.append(
                f"drawtext=fontfile='{font}':textfile='{tmp_txt['titular']}':"
                f"expansion=none:fontcolor=white:fontsize=h/16:line_spacing=10:"
                f"box=1:boxcolor=black@0.45:boxborderw=24:"
                f"x=(w-text_w)/2:y=h*0.10"
            )
        if pieza.get("cta"):
            draws.append(
                f"drawtext=fontfile='{font}':textfile='{tmp_txt['cta']}':"
                f"expansion=none:fontcolor=white:fontsize=h/28:"
                f"box=1:boxcolor=black@0.55:boxborderw=16:"
                f"x=(w-text_w)/2:y=h*0.85"
            )
        filtros.append(f"{cur}{','.join(draws)}[vout]")
        cur = "[vout]"

    filter_complex = ";".join(filtros)
    cmd += ["-filter_complex", filter_complex, "-map", cur]

    if audio:
        cmd += ["-map", f"{len(frames)}:a", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [
        "-r", str(fps), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-movflags", "+faststart", dest,
    ]
    return cmd, dest


def _editar_pieza_formato(pieza, formato, cfg, audio_dir, font):
    frames = [t["frame"] for t in pieza["tomas"] if t.get("frame")]
    if not frames:
        raise RuntimeError("sin frames")
    audio = _buscar_audio(pieza, audio_dir)

    # Titular/CTA a fichero temporal (evita todo el lío de escapes en drawtext).
    tmp_files = {}
    tmp_txt = {}
    try:
        for clave in ("titular", "cta"):
            if pieza.get(clave):
                fd, path = tempfile.mkstemp(suffix=".txt")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(str(pieza[clave]))
                tmp_files[clave] = path
                tmp_txt[clave] = path
        cmd, dest = _construir_cmd(pieza, formato, frames, cfg, audio, font, tmp_txt)
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", "ignore")[-600:]
            raise RuntimeError(f"ffmpeg falló: {err}")
        return dest
    finally:
        for path in tmp_files.values():
            if os.path.exists(path):
                os.remove(path)


def edit(semana):
    manifest = load_manifest(semana)
    cfg = manifest["config"]
    p = paths_semana(semana)
    audio_dir = p["inputs_audio"]
    font = find_font()
    if not font:
        warn("No encontré fuente DejaVu; los vídeos saldrán SIN titular.")

    editores = int(cfg.get("editores", 4))
    pendientes = [pz for pz in manifest["piezas"] if pz.get("estado") == "generado"]
    if not pendientes:
        log("[edit] nada que editar (ninguna pieza en estado 'generado').")
        return manifest

    # Una tarea por (pieza, formato) para exprimir el paralelismo.
    tareas = []
    for pz in pendientes:
        pz["_semana"] = semana  # ruta de salida; se quita antes de guardar
        for fmt in pz.get("formatos", cfg["formatos"]):
            tareas.append((pz, fmt))

    log(f"[edit] {len(pendientes)} piezas · {len(tareas)} vídeos · {editores} editores")

    fallos = {pz["id"]: [] for pz in pendientes}
    with ThreadPoolExecutor(max_workers=editores) as ex:
        fut = {ex.submit(_editar_pieza_formato, pz, fmt, cfg, audio_dir, font): (pz, fmt)
               for pz, fmt in tareas}
        for f in as_completed(fut):
            pz, fmt = fut[f]
            try:
                dest = f.result()
                pz.setdefault("salidas", {})[fmt] = dest
                log(f"  {pz['id']} [{fmt}] -> {os.path.relpath(dest, p['base'])}")
            except Exception as e:  # noqa: BLE001
                fallos[pz["id"]].append(f"{fmt}: {e}")
                warn(f"{pz['id']} [{fmt}] ERROR: {e}")

    ok = err = 0
    for pz in pendientes:
        pz.pop("_semana", None)
        esperados = set(pz.get("formatos", cfg["formatos"]))
        logrados = set(pz.get("salidas", {}).keys())
        if fallos[pz["id"]] or not esperados.issubset(logrados):
            pz["estado"] = "error"
            pz["error"] = "; ".join(fallos[pz["id"]]) or "faltan formatos"
            err += 1
        else:
            pz["estado"] = "final"
            pz["error"] = None
            ok += 1

    save_manifest(semana, manifest)
    log(f"[edit] piezas finalizadas: {ok} · con error: {err}")
    return manifest


def main():
    ap = argparse.ArgumentParser(description="Edita vídeos con ffmpeg (paralelo).")
    ap.add_argument("semana")
    args = ap.parse_args()
    edit(args.semana)


if __name__ == "__main__":
    main()
