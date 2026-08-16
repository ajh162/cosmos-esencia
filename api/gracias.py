"""
============================================================================
 COSMOS Y ESENCIA — Página de descarga después del pago
 Ruta pública: https://www.cosmosyesencia.com/api/gracias
============================================================================

 POR QUÉ EXISTE ESTE ARCHIVO:

   Hasta ahora, la única forma de recibir el PDF era el correo. Eso rompe
   la venta en tres situaciones muy comunes:

     • Mercado Pago no manda el correo del comprador (pagos en efectivo,
       transferencia o como invitado).
     • El correo cae en spam.
     • El comprador escribió mal su correo.

   En los tres casos el cliente pagó y ve una página en blanco. Con esta
   página, al volver de Mercado Pago ve su botón de descarga de inmediato.
   El correo pasa a ser el respaldo, no el único camino.

 CÓMO LLEGA AQUÍ EL COMPRADOR:

   checkout.py pone esta ruta en back_urls.success y back_urls.pending.
   Mercado Pago redirige agregando parámetros a la URL, entre ellos
   payment_id (a veces llamado collection_id). Con ese id le preguntamos
   a Mercado Pago si el pago está aprobado — nunca confiamos en lo que
   venga en la URL, porque cualquiera puede escribirla a mano.
============================================================================
"""

import os
import html
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from supabase import create_client


MP_ACCESS_TOKEN      = os.environ.get("MP_ACCESS_TOKEN", "")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SITIO_URL            = os.environ.get("SITIO_URL", "https://www.cosmosyesencia.com").rstrip("/")
CORREO_CONTACTO      = os.environ.get("CORREO_CONTACTO", "hola@cosmosyesencia.com")

BUCKET = "ebooks"
DURACION_ENLACE = 60 * 60 * 24  # 24 horas

CATALOGO = {
    "renacer": {
        "titulo": "Renacer Energético — 21 días",
        "archivos": ["renacer-energetico-21-dias.pdf"],
    },
    "matriz": {
        "titulo": "Matriz del Destino",
        "archivos": ["matriz-del-destino.pdf"],
    },
    "paquete": {
        "titulo": "Renacer Energético + Matriz del Destino",
        "archivos": [
            "renacer-energetico-21-dias.pdf",
            "matriz-del-destino.pdf",
        ],
    },
}


# ===========================================================================
# LA PÁGINA
# ---------------------------------------------------------------------------
# Usa la misma paleta, las mismas tipografías y el mismo lenguaje visual
# que index.html, para que el comprador sienta que nunca salió del sitio.
# ===========================================================================

def pagina(titular, texto, botones_html="", nota=""):
    return f"""<!DOCTYPE html>
<html lang="es-MX">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titular)} — Cosmos y Esencia</title>
<meta name="robots" content="noindex">
<link rel="icon" type="image/png" href="{SITIO_URL}/assets/favicon.png">
<meta name="theme-color" content="#131A29">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400&family=Jost:wght@200;300;400&display=swap" rel="stylesheet">
<style>
  :root {{
    --noche: #131A29;
    --superficie: #232F4C;
    --lavanda: #B9A8D6;
    --oro: #E6B96C;
    --marfil: #F7F3EE;
    --display: "Cormorant Garamond", Georgia, serif;
    --sans: "Jost", "Helvetica Neue", Arial, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 8vh 6vw;
    background: radial-gradient(120% 90% at 50% 0%, #232F4C 0%, #131A29 62%);
    color: rgba(247,243,238,.86);
    font-family: var(--sans);
    font-weight: 300;
    line-height: 1.7;
    text-align: center;
  }}
  .caja {{ max-width: 34rem; }}
  .eclipse {{ color: var(--oro); opacity: .9; margin-bottom: 1.5rem; }}
  h1 {{
    font-family: var(--display);
    font-weight: 300;
    font-size: clamp(2rem, 6vw, 3rem);
    line-height: 1.15;
    color: var(--marfil);
    margin: 0 0 1rem;
  }}
  p {{ margin: 0 0 1.25rem; }}
  .btn {{
    display: inline-block;
    margin: .5rem .35rem;
    padding: 1rem 2.2rem;
    border-radius: 999px;
    background: var(--oro);
    color: var(--noche);
    text-decoration: none;
    font-size: .82rem;
    letter-spacing: .16em;
    text-transform: uppercase;
    transition: transform .2s ease, box-shadow .2s ease;
  }}
  .btn:hover, .btn:focus-visible {{
    transform: translateY(-2px);
    box-shadow: 0 10px 30px rgba(230,185,108,.28);
  }}
  .btn--ghost {{
    background: transparent;
    color: var(--lavanda);
    border: 1px solid rgba(185,168,214,.34);
  }}
  .nota {{
    margin-top: 2rem;
    font-size: .82rem;
    color: rgba(185,168,214,.8);
    line-height: 1.6;
  }}
  a {{ color: var(--lavanda); }}
  :focus-visible {{ outline: 2px solid var(--oro); outline-offset: 3px; }}
  @media (prefers-reduced-motion: reduce) {{
    .btn {{ transition: none; }}
    .btn:hover {{ transform: none; }}
  }}
</style>
</head>
<body>
  <div class="caja">
    <svg class="eclipse" width="44" height="44" viewBox="0 0 48 48" aria-hidden="true">
      <circle cx="24" cy="24" r="15" fill="none" stroke="currentColor" stroke-width="1" opacity=".55"/>
      <path d="M24 9a15 15 0 0 1 0 30" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
    </svg>
    <h1>{html.escape(titular)}</h1>
    <p>{texto}</p>
    {botones_html}
    <p class="nota">{nota}</p>
  </div>
</body>
</html>"""


def boton(url, etiqueta):
    return f'<p><a class="btn" href="{html.escape(url, quote=True)}">{html.escape(etiqueta)}</a></p>'


def volver():
    return f'<p><a class="btn btn--ghost" href="{SITIO_URL}/">Volver al inicio</a></p>'


class handler(BaseHTTPRequestHandler):

    def _enviar(self, codigo, html_texto):
        cuerpo = html_texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        # Sin caché: cada enlace de descarga es distinto y caduca.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        try:
            parametros = parse_qs(urlparse(self.path).query)

            # Mercado Pago usa payment_id o collection_id según el flujo.
            payment_id = (
                parametros.get("payment_id", [""])[0]
                or parametros.get("collection_id", [""])[0]
            ).strip()

            if not payment_id or payment_id.lower() == "null":
                return self._enviar(200, pagina(
                    "No encontramos tu pago",
                    "Llegaste a esta página sin un pago asociado. Si ya pagaste, "
                    "revisa tu correo: ahí está tu enlace de descarga.",
                    volver(),
                    f'¿Necesitas ayuda? Escríbenos a <a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a>.'
                ))

            # Nunca confiamos en la URL: le preguntamos a Mercado Pago.
            respuesta = requests.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
                timeout=10,
            )
            respuesta.raise_for_status()
            pago = respuesta.json()
            estado = pago.get("status")

            if estado != "approved":
                # Caso típico: pago en OXXO o transferencia, aún sin acreditar.
                return self._enviar(200, pagina(
                    "Tu pago está en proceso",
                    "En cuanto se acredite, te enviamos el enlace de descarga por "
                    "correo. Con pagos en efectivo o transferencia esto puede "
                    "tardar unas horas.",
                    volver(),
                    f'Si pasan 24 horas y no llega, escríbenos a <a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a> '
                    f'con tu número de pago: {html.escape(payment_id)}'
                ))

            referencia = (pago.get("external_reference") or "").strip().lower()
            producto = CATALOGO.get(referencia)

            if not producto:
                print("Referencia desconocida en /gracias:", referencia, payment_id)
                return self._enviar(200, pagina(
                    "Tu pago se aprobó",
                    "Estamos preparando tu descarga y te la enviamos por correo "
                    "en unos minutos.",
                    volver(),
                    f'Si no llega, escríbenos a <a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a> '
                    f'con tu número de pago: {html.escape(payment_id)}'
                ))

            # Generamos los enlaces temporales, igual que en el webhook.
            supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            botones = ""
            for i, archivo in enumerate(producto["archivos"], start=1):
                resultado = supabase.storage.from_(BUCKET).create_signed_url(
                    archivo, DURACION_ENLACE
                )
                url = resultado.get("signedURL") or resultado.get("signedUrl")
                if url:
                    etiqueta = "Descargar mi PDF" if len(producto["archivos"]) == 1 \
                        else f"Descargar PDF {i}"
                    botones += boton(url, etiqueta)

            if not botones:
                print("No se generaron Signed URLs en /gracias para", referencia)
                return self._enviar(200, pagina(
                    "Tu pago se aprobó",
                    "Tuvimos un problema al preparar tu archivo. Escríbenos y te "
                    "lo enviamos enseguida.",
                    volver(),
                    f'<a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a> · '
                    f'Número de pago: {html.escape(payment_id)}'
                ))

            return self._enviar(200, pagina(
                "Tu cuaderno está listo",
                f"Gracias por tu compra de <strong>{html.escape(producto['titulo'])}</strong>. "
                "También te lo enviamos por correo.",
                botones + volver(),
                "El enlace es personal y caduca en 24 horas. Descarga el archivo "
                "y guárdalo en tu dispositivo."
            ))

        except Exception as error:
            print("ERROR en /api/gracias:", repr(error))
            return self._enviar(200, pagina(
                "Algo salió mal de nuestro lado",
                "Si tu pago se completó, tu enlace va en camino por correo.",
                volver(),
                f'¿No llega? Escríbenos a <a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a>.'
            ))

    def log_message(self, formato, *args):
        return