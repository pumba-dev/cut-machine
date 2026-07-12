"""Estagio compartilhado de encaixe do video na janela (short_frame.py / corte_frame.py).

Sem `crop_segments`: crop-to-fill classico — a janela e preenchida por inteiro
(escala ate cobrir + corta o excesso), sem barra preta. E o fallback estatico
quando a conta nao tem reframe dinamico ativo (core.render.reframe, opt-in).

Com `crop_segments`: cada segmento (recorte de "camera" ao redor de quem fala)
vira seu proprio trim+crop+scale, concatenados por corte seco — e o reframe da
Fase 4. Os segmentos DEVEM cobrir [0, duracao_total] sem buracos nem overlap
(reframe.py garante isso, preenchendo os trechos sem speaker resolvido com o
crop central classico).
"""


def even(n: float) -> int:
    """Maior inteiro par <= n (dimensoes de video precisam ser pares p/ yuv420p)."""
    v = int(n)
    return v - (v % 2)


def build_video_stage(ew: int, eh: int, crop_segments: list[dict] | None,
                      out_label: str = "fg") -> str:
    """Filtro de video partindo de `[0:v]` ja com `setpts`+`vfx` aplicados por
    fora (o chamador prefixa `[0:v]setpts=PTS-STARTPTS,{vfx}` antes deste
    fragmento) -> `[out_label]` do tamanho exato ew x eh (ambos ja pares).

    `crop_segments`: lista opcional de {start, end, x, y, w, h} — tempo LOCAL do
    clip em segundos, regiao em fracao 0-1 do frame fonte (x,y = canto superior
    esquerdo; w,h = tamanho). None/vazio = crop-to-fill unico cobrindo o clip
    inteiro (comportamento classico).
    """
    if not crop_segments:
        return (f"scale={ew}:{eh}:force_original_aspect_ratio=increase,"
                f"crop={ew}:{eh}[{out_label}]")

    n = len(crop_segments)
    if n == 1:
        seg = crop_segments[0]
        return (
            f"crop=w=iw*{seg['w']:.4f}:h=ih*{seg['h']:.4f}:"
            f"x=iw*{seg['x']:.4f}:y=ih*{seg['y']:.4f},"
            f"scale={ew}:{eh}:force_original_aspect_ratio=increase,"
            f"crop={ew}:{eh}[{out_label}]"
        )

    graph = [f"split={n}" + "".join(f"[{out_label}_s{i}]" for i in range(n))]
    seg_labels = []
    for i, seg in enumerate(crop_segments):
        lbl = f"{out_label}_c{i}"
        seg_labels.append(f"[{lbl}]")
        graph.append(
            f"[{out_label}_s{i}]trim={seg['start']:.3f}:{seg['end']:.3f},"
            "setpts=PTS-STARTPTS,"
            f"crop=w=iw*{seg['w']:.4f}:h=ih*{seg['h']:.4f}:"
            f"x=iw*{seg['x']:.4f}:y=ih*{seg['y']:.4f},"
            f"scale={ew}:{eh}:force_original_aspect_ratio=increase,"
            # setsar=1: cada segmento croppa uma regiao FONTE diferente, entao o
            # SAR calculado pelo scale (mesmo com o w x h de saida identico)
            # pode divergir por arredondamento entre segmentos -- `concat`
            # rejeita entradas com SAR diferente mesmo com resolucao igual.
            f"crop={ew}:{eh},setsar=1[{lbl}]"
        )
    graph.append("".join(seg_labels) + f"concat=n={n}:v=1:a=0[{out_label}]")
    return ";".join(graph)
