"""Exportación a PDF con las medidas del formato profesional.

Escritor de PDF propio, sin dependencias externas: el proyecto debe correr en
cualquier Python 3.9+ sin instalar nada que compile.

Medidas verificadas sobre un guion real en Final Draft 13:
  - página carta 612 x 792 pt
  - número de escena / timecode: x = 54
  - encabezado y acción:         x = 108, ancho 6,0 pulg.
  - diálogo:                     x = 180, ancho 3,5 pulg.
  - personaje:                   x = 252
  - Courier 12 pt, interlineado 12 pt
El código de tiempo sustituye al número de escena.
"""
from __future__ import annotations

PAGINA_ANCHO, PAGINA_ALTO = 612.0, 792.0
X_TC, X_ACCION, X_DIALOGO, X_PERSONAJE = 54.0, 108.0, 180.0, 252.0
ANCHO_ACCION = 6.0 * 72
ANCHO_DIALOGO = 3.5 * 72
TAM = 12.0
INTERLINEADO = 12.0
MARGEN_INFERIOR = 72.0
AVANCE_COURIER = 0.6  # ancho de carácter de Courier, en múltiplos del cuerpo


# --------------------------------------------------------------- utilidades
def _ancho_texto(texto: str, tam: float = TAM) -> float:
    return len(texto) * tam * AVANCE_COURIER


def _envolver(texto: str, ancho: float, tam: float = TAM) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for w in palabras:
        prueba = f"{actual} {w}".strip()
        if _ancho_texto(prueba, tam) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = w
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _escapar(texto: str) -> bytes:
    """Escape de cadenas PDF y codificación WinAnsi (acentos, comillas latinas)."""
    t = texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    try:
        return t.encode("cp1252")
    except UnicodeEncodeError:
        return t.encode("cp1252", "replace")


class _Pagina:
    def __init__(self) -> None:
        self.ops: list[bytes] = []

    def texto(self, x: float, y: float, contenido: str, tam: float = TAM,
              negrita: bool = False) -> None:
        fuente = b"/F2" if negrita else b"/F1"
        y_pdf = PAGINA_ALTO - y
        self.ops.append(
            b"BT " + fuente + b" " + f"{tam:.2f}".encode() + b" Tf "
            + f"1 0 0 1 {x:.2f} {y_pdf:.2f} Tm (".encode()
            + _escapar(contenido) + b") Tj ET"
        )

    def contenido(self) -> bytes:
        return b"\n".join(self.ops)


def _ensamblar(paginas: list[_Pagina]) -> bytes:
    """Construye el archivo PDF con su tabla de referencias cruzadas."""
    n = len(paginas)
    catalog, pages_obj, first_page = 1, 2, 3
    page_ids = [first_page + 2 * i for i in range(n)]
    content_ids = [pid + 1 for pid in page_ids]
    font_reg = first_page + 2 * n
    font_bold = font_reg + 1
    total = font_bold + 1

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}

    def obj(num: int, cuerpo: bytes) -> None:
        offsets[num] = len(out)
        out.extend(f"{num} 0 obj\n".encode())
        out.extend(cuerpo)
        out.extend(b"\nendobj\n")

    obj(catalog, f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode())
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    obj(pages_obj, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())

    for pid, cid, pagina in zip(page_ids, content_ids, paginas):
        obj(pid, (
            f"<< /Type /Page /Parent {pages_obj} 0 R "
            f"/MediaBox [0 0 {PAGINA_ANCHO:.0f} {PAGINA_ALTO:.0f}] "
            f"/Resources << /Font << /F1 {font_reg} 0 R /F2 {font_bold} 0 R >> >> "
            f"/Contents {cid} 0 R >>"
        ).encode())
        cuerpo = pagina.contenido()
        obj(cid, f"<< /Length {len(cuerpo)} >>\nstream\n".encode() + cuerpo + b"\nendstream")

    obj(font_reg, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier "
                  b"/Encoding /WinAnsiEncoding >>")
    obj(font_bold, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold "
                   b"/Encoding /WinAnsiEncoding >>")

    inicio_xref = len(out)
    out.extend(f"xref\n0 {total}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for numero in range(1, total):
        out.extend(f"{offsets[numero]:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {total} /Root {catalog} 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n".encode()
    )
    return bytes(out)


# ------------------------------------------------------------------- export
def generar(guion: dict, brief: dict, ruta: str) -> str:
    paginas: list[_Pagina] = []
    pagina = _Pagina()
    y = 72.0
    numero_pagina = 1

    def numerar() -> None:
        pagina.texto(PAGINA_ANCHO - 72, 44, f"{numero_pagina}.", tam=12)

    def nueva_pagina() -> None:
        nonlocal pagina, y, numero_pagina
        paginas.append(pagina)
        pagina = _Pagina()
        numero_pagina += 1
        y = 72.0
        numerar()

    numerar()

    def escribir(texto: str, x: float, ancho: float, sangria: float = 0.0) -> None:
        nonlocal y
        for linea in _envolver(texto, ancho - sangria):
            if y > PAGINA_ALTO - MARGEN_INFERIOR:
                nueva_pagina()
            pagina.texto(x + sangria, y, linea)
            y += INTERLINEADO

    for p in guion["parrafos"]:
        tipo, texto = p["tipo"], p["texto"]
        if y > PAGINA_ALTO - 96:
            nueva_pagina()

        if tipo == "scene_heading":
            if p.get("tc"):
                pagina.texto(X_TC, y, p["tc"], negrita=True)
            escribir(texto.upper(), X_ACCION, ANCHO_ACCION)
            y += INTERLINEADO * 0.5

        elif tipo == "action":
            escribir(texto, X_ACCION, ANCHO_ACCION)
            y += INTERLINEADO * 0.5

        elif tipo == "character":
            pagina.texto(X_PERSONAJE, y, texto.upper())
            y += INTERLINEADO

        elif tipo == "parenthetical":
            escribir(f"({texto.strip('()')})", X_DIALOGO, ANCHO_DIALOGO, sangria=12)
            y += INTERLINEADO * 0.25

        elif tipo == "dialogue":
            escribir(texto, X_DIALOGO, ANCHO_DIALOGO)
            y += INTERLINEADO * 0.5

        elif tipo == "transition":
            pagina.texto(PAGINA_ANCHO - 108 - _ancho_texto(texto.upper()), y,
                         texto.upper())
            y += INTERLINEADO

        elif tipo == "title":
            pagina.texto((PAGINA_ANCHO - _ancho_texto(texto.upper())) / 2, y,
                         texto.upper(), negrita=True)
            y += INTERLINEADO * 1.5

    paginas.append(pagina)

    with open(ruta, "wb") as f:
        f.write(_ensamblar(paginas))
    return ruta

