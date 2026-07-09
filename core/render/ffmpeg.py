"""Montagem de comandos ffmpeg e renderizacao de clips.

Corte preciso exige re-encode: stream copy so inicia em keyframe e o corte
gruda no IDR anterior/posterior. -ss antes de -i (seek rapido + decode ate
o ponto exato) faz o output comecar em t=0, por isso o ASS usa tempos
rebased.
"""
import os
import subprocess
from pathlib import Path

from .. import paths
from ..contracts import FORMAT_RULES
from ..media import video_info
from .branding import build_border_ass, build_corte_filter, resolve_brand
from .captions import build_ass
from .corte_frame import BG_FALLBACK as CORTE_BG_FALLBACK
from .corte_frame import build_corte_frame_filter
from .intro import prepend_intro
from .outro import append_outro
from .short_frame import BG_FALLBACK, build_short_filter
from .thumbnail import generate_thumbnail
from .thumbnail_config import composite_enabled, intro_enabled, resolve_thumbnail
from .transform import (
    audio_active,
    build_audio_graph,
    pick_music,
    resolve_transform,
    seed_for,
    speed_factor,
)
from .transform import summary as transform_summary
from .transform import video_filters


def _t(value: float) -> str:
    return f"{float(value):.3f}"


def _resolve_frame_png(rel: str | None) -> str | None:
    """Caminho absoluto do PNG de moldura (short/corte), ou None se ausente/inexistente.

    Path relativo e resolvido a partir da raiz do repo. Retornar absoluto e
    seguro no `-i` do ffmpeg (so o filtro `ass=` sofre com escaping no Windows).
    """
    if not rel or not str(rel).strip():
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = paths.ROOT / rel
    return str(p.resolve()) if p.exists() else None


def build_short_cmd(start: float, dur: float, captions_ass: str,
                    out_filename: str, source: str = "source.mp4",
                    frame_png: str | None = None, bg_hex: str = BG_FALLBACK,
                    vfx: str = "", audio_graph: str = "",
                    music_path: str | None = None,
                    dur_read: float | None = None) -> list[str]:
    """Comando ffmpeg para short 1080x1920 com moldura fixa + legendas queimadas.

    Fundo ESTATICO (nao mais blur): arte PNG decorativa da conta (`frame_png`,
    caminho absoluto — seguro em `-i`, ao contrario do filtro `ass=`) ou, sem
    PNG, uma cor chapada (`bg_hex`). O video 16:9 entra SEM CROP numa janela
    (escala por largura, altura par via `-2`) e a arte e sobreposta POR CIMA
    (janela transparente). Toda a marca/CTA ja vem embutida na arte PNG; so
    `captions_ass` (legendas) e queimado por cima, por nome relativo ao cwd.
    `-map 0:a?` torna o audio opcional (fonte sem audio nao quebra o comando).

    `-t _t(dur)` na SAIDA e obrigatorio: as fontes sinteticas do filtro (color +
    `-loop 1` no PNG) sao infinitas e o `overlay(...:shortest=1)` sozinho NAO
    encerra o grafo de dois overlays (`-t` no input so limita a leitura do
    video); sem o `-t` de saida o encode nunca termina.

    Transform (core.render.transform, opt-in): `vfx` insere filtros de video
    (speed/zoom/cor); `audio_graph` (subgrafo -> [aout]) substitui o passthrough
    de audio (`-map [aout]` em vez de `-map 0:a?`) para pitch/EQ/musica/speed;
    `music_path` adiciona a faixa como input (`-stream_loop -1`, indice
    1+has_png); `dur_read` (= dur*speed) le mais da fonte na ENTRADA enquanto a
    SAIDA fica travada em `dur` — mantendo a duracao invariante sob speed.
    """
    has_png = bool(frame_png)
    filter_complex = build_short_filter(bg_hex, has_png, captions_ass, vfx=vfx)
    if audio_graph:
        filter_complex = filter_complex + ";" + audio_graph
    read = dur if dur_read is None else dur_read
    cmd = ["ffmpeg", "-ss", _t(start), "-t", _t(read), "-i", source]
    if has_png:
        cmd += ["-loop", "1", "-i", frame_png]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", music_path]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", ("[aout]" if audio_graph else "0:a?"),
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", _t(dur),
        "-y", out_filename,
    ]
    return cmd


def build_corte_cmd(start: float, dur: float, out_filename: str,
                    source: str = "source.mp4",
                    filter_complex: str | None = None,
                    frame_png: str | None = None,
                    audio_graph: str = "", music_path: str | None = None,
                    dur_read: float | None = None) -> list[str]:
    """Comando ffmpeg para corte 1920x1080.

    Com `filter_complex` (moldura de marca) aplica a cadeia -> [v] e mapeia
    video+audio explicitamente (`-map [v] -map 0:a?`, audio opcional). Sem
    ele, corte cru sem filtro de video (mapeamento default). filter_complex
    referencia o .border.ass por nome relativo ao cwd do processo.

    Com `frame_png` (caminho absoluto), adiciona a arte da moldura como 2o input
    (`-loop 1`); o proprio `filter_complex` deve entao vir de
    `build_corte_frame_filter` (video sob a arte, janela transparente).

    `-t _t(dur)` na SAIDA e obrigatorio quando ha `filter_complex` com fontes
    sinteticas (color + `-loop 1` no PNG): elas sao infinitas e o
    `overlay(...:shortest=1)` sozinho NAO encerra o grafo de dois overlays (o
    `-t` de input so limita a leitura do video); sem ele o encode nunca termina.

    Transform (core.render.transform, opt-in): `audio_graph` (subgrafo -> [aout])
    substitui o passthrough de audio; o `filter_complex` de video ja vem com o
    `vfx` embutido pelo chamador. `music_path` adiciona a faixa como input
    (`-stream_loop -1`, indice 1+has_png); `dur_read` (= dur*speed) le mais da
    fonte na ENTRADA com a SAIDA travada em `dur` (duracao invariante sob speed).
    Sem filter_complex de video mas com audio_graph, o video e mapeado cru (`0:v`).
    """
    has_png = bool(frame_png)
    fc = filter_complex
    if audio_graph:
        fc = (fc + ";" + audio_graph) if fc else audio_graph
    read = dur if dur_read is None else dur_read
    cmd = ["ffmpeg", "-ss", _t(start), "-t", _t(read), "-i", source]
    if has_png:
        cmd += ["-loop", "1", "-i", frame_png]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", music_path]
    if fc:
        cmd += ["-filter_complex", fc,
                "-map", ("[v]" if filter_complex else "0:v"),
                "-map", ("[aout]" if audio_graph else "0:a?"),
                "-r", "30"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", _t(dur),
        "-y", out_filename,
    ]
    return cmd


def render_clip(clip: dict, video_id: str, transcript: dict | None = None,
                account: dict | None = None) -> dict:
    """Renderiza um clip e valida o resultado contra FORMAT_RULES.

    Gera o .ass quando o formato queima legendas, aplica a moldura de marca
    quando o formato tem `border` (corte), roda o ffmpeg e valida o output
    (resolucao exata, duracao end-start +-0.5s, audio presente). Depois gera
    a miniatura (thumbnail) do clip. Retorna o dict de core.media.video_info
    do mp4, acrescido de `thumbnail_path`/`thumbnail_ts` (ou `thumbnail_error`
    se a miniatura falhar — nunca fatal) e `transform` (parametros anti-deteccao
    aplicados, se houver). `account` fornece o brand da borda + o bloco transform.
    """
    fmt = clip["format"]
    rules = FORMAT_RULES[fmt]
    brand = resolve_brand(account)
    start = float(clip["start"])
    dur = float(clip["end"]) - start

    source = paths.source_video_path(video_id)
    if not source.exists():
        raise FileNotFoundError(f"source.mp4 nao encontrado: {source}")

    out_path = paths.clip_output_path(video_id, clip["id"])
    clip_dir = out_path.parent
    clip_dir.mkdir(parents=True, exist_ok=True)
    # cwd na pasta do clip + caminhos relativos: path absoluto dentro do
    # filtro ass= exige escaping duplo no Windows e quebra facil.
    source_rel = os.path.relpath(source, clip_dir)
    # id do YouTube pode comecar com '-'; sem o prefixo ./ o ffmpeg leria o
    # nome do output como opcao.
    out_name = "./" + out_path.name

    # --- Camada de transformacao anti-deteccao (opt-in por conta, deterministica
    # por clip). Duracao/resolucao ficam invariantes: `dur_read` (= dur*speed) le
    # mais da fonte na entrada com a saida travada em `dur`. Fonte sem audio
    # desliga speed/audio (evita erro de [0:a]; o QA ja reprovaria por falta de
    # audio de qualquer modo).
    cfg = resolve_transform(account)
    seed = seed_for(clip["id"])
    src_info = video_info(source)
    audio_ok = bool(src_info.get("has_audio"))
    vcfg = cfg if audio_ok else {**cfg, "speed": 1.0}
    speed = speed_factor(vcfg, seed)
    vfx = video_filters(vcfg, seed)
    music_path = pick_music(cfg, seed) if audio_ok else None
    dur_read = dur * speed
    src_dur = float(src_info.get("duration_s") or 0.0)
    if src_dur and start + dur_read > src_dur:
        dur_read = max(dur, src_dur - start)

    def _audio_for(has_png: bool) -> tuple[str, str | None]:
        """audio_graph + music_path efetivos para este formato (indice da musica
        depende do PNG: source=0, png=1, musica=ultimo)."""
        if not audio_ok or not audio_active(cfg, seed, music_path is not None):
            return "", None
        m_idx = (1 + (1 if has_png else 0)) if music_path else None
        return build_audio_graph(cfg, seed, music_index=m_idx, speed=speed), music_path

    if rules["burn_captions"]:
        if not transcript:
            raise ValueError(f"{clip['id']}: formato {fmt} exige transcript para legendas")
        ass_path = paths.clip_ass_path(video_id, clip["id"])
        ass_path.write_text(build_ass(clip, transcript, speed=speed), encoding="utf-8")
        frame_png = _resolve_frame_png(brand.get("short_frame"))
        audio_graph, music = _audio_for(bool(frame_png))
        cmd = build_short_cmd(
            start, dur, ass_path.name, out_name, source=source_rel,
            frame_png=frame_png, bg_hex=brand.get("short_bg_color", BG_FALLBACK),
            vfx=vfx, audio_graph=audio_graph, music_path=music, dur_read=dur_read,
        )
    elif rules.get("border"):
        corte_png = _resolve_frame_png(brand.get("corte_frame"))
        if corte_png:
            # Arte PNG estatica (janela fixa) substitui a moldura gerada.
            fc = build_corte_frame_filter(CORTE_BG_FALLBACK, has_png=True, vfx=vfx)
            audio_graph, music = _audio_for(True)
            cmd = build_corte_cmd(start, dur, out_name, source=source_rel,
                                  filter_complex=fc, frame_png=corte_png,
                                  audio_graph=audio_graph, music_path=music,
                                  dur_read=dur_read)
        else:
            # Fallback: moldura gerada (padding + rim + faixa de texto ASS).
            border_ass = paths.clip_border_ass_path(video_id, clip["id"])
            border_ass.write_text(build_border_ass(brand), encoding="utf-8")
            fc = build_corte_filter(brand, border_ass.name, vfx=vfx)
            audio_graph, music = _audio_for(False)
            cmd = build_corte_cmd(start, dur, out_name, source=source_rel,
                                  filter_complex=fc, audio_graph=audio_graph,
                                  music_path=music, dur_read=dur_read)
    else:
        audio_graph, music = _audio_for(False)
        cmd = build_corte_cmd(start, dur, out_name, source=source_rel,
                              audio_graph=audio_graph, music_path=music,
                              dur_read=dur_read)

    proc = subprocess.run(
        cmd, cwd=str(clip_dir), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg falhou (exit {proc.returncode}): {tail}")

    info = video_info(out_path)
    problems: list[str] = []
    resolution = f"{info['width']}x{info['height']}"
    if resolution != rules["resolution"]:
        problems.append(f"resolucao {resolution}, esperada {rules['resolution']}")
    if abs(info["duration_s"] - dur) > 0.5:
        problems.append(f"duracao {info['duration_s']:.2f}s, esperada {dur:.2f}s (+-0.5s)")
    if not info["has_audio"]:
        problems.append("sem stream de audio")
    if problems:
        raise ValueError(f"{out_path.name} invalido: " + "; ".join(problems))

    # --- Miniatura: gerada AQUI (antes da intro, que usa a imagem da thumb) e
    # SEMPRE best-effort — nunca derruba o clip. Precedencia (degrada em cascata):
    #   1) compositada local (default das contas face_aware) — fundo+recorte+glow+texto,
    #      9:16/16:9 exato, gratis e deterministica, pessoa 100% fiel;
    #   2) thumb ASS simples (crop central) — fallback final.
    # O check de conteudo (duracao/resolucao) ja rodou isolado acima.
    tcfg = resolve_thumbnail(account)
    thumb_img = None
    try:
        thumb, provider = None, "local"
        if composite_enabled(tcfg):
            try:
                thumb = _composite_thumbnail(clip, video_id, tcfg, account)
                provider = thumb.get("provider", "local_composite")
            except Exception as exc:  # noqa: BLE001 — composite cai na thumb ASS
                info["thumbnail_composite_error"] = str(exc) or exc.__class__.__name__
                thumb = None
        if thumb is None:
            thumb = generate_thumbnail(clip, video_id)
            provider = "local"
        info["thumbnail_path"] = thumb["path"]
        info["thumbnail_ts"] = thumb["ts"]
        info["thumbnail_provider"] = provider
        thumb_img = thumb["path"]
    except Exception as exc:  # noqa: BLE001 — miniatura nunca e fatal
        info["thumbnail_error"] = str(exc) or exc.__class__.__name__

    # Intro (opt-in, so short): cola a thumb como ~1s congelado no INICIO (capa
    # do feed do Shorts). Roda apos a validacao do conteudo (isolada). Falha =
    # SKIP nao-fatal (bonus, depende da thumb best-effort). `intro_duration_s`
    # so e gravado quando de fato aplicado (senao o QA desincroniza a duracao).
    if thumb_img is not None and intro_enabled(tcfg, fmt):
        try:
            added = prepend_intro(out_path, thumb_img, rules["resolution"],
                                  duration_s=float(tcfg["intro_duration_s"]))
            info["intro_duration_s"] = added
            info["duration_s"] = video_info(out_path)["duration_s"]
        except Exception as exc:  # noqa: BLE001 — intro nao e fatal
            info["intro_error"] = str(exc) or exc.__class__.__name__

    # Vinheta de fim (opt-in por conta): cola a arte de outro ao FINAL do mp4 ja
    # validado. So DEPOIS do check de conteudo (que roda sobre `dur`, sem intro/
    # outro): o corte/composicao do conteudo e validado isolado; intro/outro so
    # estendem a duracao. Fatal em falha (a vinheta e requisito de marca, ao
    # contrario da miniatura/intro). `_resolve_frame_png` resolve o path.
    outro_path = _resolve_frame_png(brand.get(f"{fmt}_outro"))
    if outro_path:
        crf = 18 if fmt == "short" else 20
        added = append_outro(out_path, outro_path, rules["resolution"], crf=crf)
        info["outro_duration_s"] = added
        info["duration_s"] = video_info(out_path)["duration_s"]

    # Parametros de transformacao efetivamente aplicados (auditoria/reproducao).
    tsum = transform_summary(cfg, seed, speed=speed, music_path=music_path)
    if tsum:
        info["transform"] = tsum
    return info


def _composite_thumbnail(clip: dict, video_id: str, tcfg: dict, account: dict | None) -> dict:
    """Wrapper lazy da thumb compositada local (core.render.thumbnail_local):
    importa so quando usada, para nao exigir rembg/Pillow em quem nao usa."""
    from .thumbnail_local import generate_thumbnail_composite
    return generate_thumbnail_composite(clip, video_id, tcfg, account)
