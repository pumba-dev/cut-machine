"""Smoke test das molduras fixas (short 9:16 e corte 16:9).

Renderiza um clip REAL (arte PNG de fundo + video sem crop na janela [+ legendas
queimadas, so no short]) para uma pasta de preview e extrai frames para inspecao
visual. NAO altera o estado do pipeline (clips.json/state.json) — so le.

Uso:
    python scripts/smoke_frame.py [--format short|corte] [--video-id ID]
        [--clip CLIP_ID] [--account ID] [--seconds N | --full] [--frames N]

Sem --video-id, escolhe o primeiro video em video-output/ que tenha
source.mp4 + transcript.json + um clip do formato pedido. Saida (gitignored):
video-output/_smoke_frame/<clip_id>/ (mp4 + frame_NN.png).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import accounts, contracts, paths
from core.render import corte_frame, short_frame
from core.render.branding import resolve_brand
from core.render.captions import build_ass
from core.render.ffmpeg import (
    _resolve_frame_png,
    build_corte_cmd,
    build_short_cmd,
)


def _pick_video(explicit: str | None, fmt: str) -> str | None:
    if explicit:
        return explicit
    for d in sorted(p for p in paths.OUTPUT_ROOT.glob("*") if p.is_dir()):
        vid = d.name
        if vid.startswith("_"):
            continue
        if (paths.source_video_path(vid).exists()
                and paths.transcript_path(vid).exists()
                and paths.clips_path(vid).exists()):
            plan = contracts.load_plan(paths.clips_path(vid))
            if any(c.get("format") == fmt for c in plan["clips"]):
                return vid
    return None


def _run(cmd: list[str], cwd: Path) -> int:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  ffmpeg stderr:", (r.stderr or "")[-1200:])
    return r.returncode


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke test das molduras fixas")
    ap.add_argument("--format", choices=["short", "corte"], default="short")
    ap.add_argument("--video-id", default=None)
    ap.add_argument("--clip", default=None, help="clip_id especifico do formato")
    ap.add_argument("--account", default="principal")
    ap.add_argument("--seconds", type=float, default=8.0,
                    help="duracao do preview em s (0 ou --full = clip inteiro)")
    ap.add_argument("--full", action="store_true", help="renderiza o clip inteiro")
    ap.add_argument("--frames", type=int, default=4, help="quantos frames extrair")
    args = ap.parse_args()

    fmt = args.format
    video_id = _pick_video(args.video_id, fmt)
    if not video_id:
        print(f"ERRO: nenhum video com source+transcript+{fmt} em video-output/")
        sys.exit(2)

    plan = contracts.load_plan(paths.clips_path(video_id))
    clips = [c for c in plan["clips"] if c.get("format") == fmt]
    if not clips:
        print(f"ERRO: {video_id} nao tem clip {fmt}"); sys.exit(2)
    if args.clip:
        clip = next((c for c in clips if c["id"] == args.clip), None)
        if clip is None:
            print(f"ERRO: {fmt} {args.clip} nao existe em {video_id}"); sys.exit(2)
    else:
        clip = clips[0]

    if not paths.source_video_path(video_id).exists():
        print("ERRO: source.mp4 ausente"); sys.exit(2)
    brand = resolve_brand(accounts.get_account("youtube", args.account))

    out = paths.OUTPUT_ROOT / "_smoke_frame" / clip["id"]
    out.mkdir(parents=True, exist_ok=True)

    start = float(clip["start"])
    full = float(clip["end"]) - start
    dur = full if (args.full or args.seconds <= 0) else min(full, args.seconds)
    src_rel = os.path.relpath(paths.source_video_path(video_id), out)
    mp4 = f"./{clip['id']}.mp4"

    if fmt == "short":
        png = _resolve_frame_png(brand.get("short_frame"))
        window = short_frame.WINDOW
        transcript = json.loads(paths.transcript_path(video_id).read_text(encoding="utf-8"))
        ass = out / f"{clip['id']}.ass"
        ass.write_text(build_ass(clip, transcript), encoding="utf-8")
        cmd = build_short_cmd(start, dur, ass.name, mp4, source=src_rel,
                              frame_png=png, bg_hex=brand.get("short_bg_color", "#111111"))
    else:
        png = _resolve_frame_png(brand.get("corte_frame"))
        window = corte_frame.WINDOW
        fc = corte_frame.build_corte_frame_filter(corte_frame.BG_FALLBACK, has_png=bool(png))
        cmd = build_corte_cmd(start, dur, mp4, source=src_rel,
                              filter_complex=fc, frame_png=png)

    print(f"format={fmt} video={video_id} clip={clip['id']} "
          f"start={start:.2f} dur={dur:.2f}s (clip inteiro={full:.1f}s)")
    print(f"PNG={png or '(fallback solido)'}")
    print(f"WINDOW (x,y,w,h)={window}")

    if _run(cmd, out) != 0:
        print("FALHOU no render"); sys.exit(1)

    n = max(1, args.frames)
    shots = []
    for i in range(n):
        ts = dur * (i + 0.5) / n
        shot = f"./frame_{i:02d}.png"
        if _run(["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", mp4,
                 "-frames:v", "1", shot], out) == 0:
            shots.append(out / f"frame_{i:02d}.png")

    print("\nOK. Confira:")
    print("  video:", out / f"{clip['id']}.mp4")
    for s in shots:
        print("  frame:", s)


if __name__ == "__main__":
    main()
