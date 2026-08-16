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

   Con esta página, al volver de Mercado Pago ve su botón de descarga de
   inmediato. El correo pasa a ser el respaldo, no el único camino.

 ── CAMBIOS DE ESTA VERSIÓN (lo visual) ────────────────────────────────────

   ANTES esta página traía su propio CSS copiado a mano: fondo plano, un
   eclipse dibujado en SVG y nada de movimiento. Se parecía al sitio,
   pero no era el sitio.

   AHORA carga los MISMOS archivos que index.html:

       /css/styles.css   → la hoja de estilos completa de la marca
       /js/cielo.js      → el cielo animado (estrellas, nebulosas,
                            constelaciones, fugaces, polvo estelar)

   y monta las mismas tres capas de fondo. Resultado: el comprador no
   siente que salió a otra página.

   VENTAJA IMPORTANTE: el día que cambies un color o una animación en
   styles.css, esta página cambia sola. No hay dos copias que mantener.

   El círculo del eclipse se cambió por assets/eclipse.png, el logo real.

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
CORREO_CONTACTO      = os.environ.get("CORREO_CONTACTO", "cosmosyesencia@gmail.com")

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
# Reutiliza styles.css y cielo.js del sitio. Solo lleva un bloque pequeño
# de CSS propio para centrar el contenido, porque esta pantalla no tiene
# las secciones largas de index.html.
#
# NOTA PARA CUANDO LO EDITES: este texto es un f-string de Python, así que
# las llaves del CSS van DOBLES ({{ y }}). Si escribes una sola, Python
# creerá que es una variable y truena al desplegar.
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
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=Jost:wght@200;300;400;500&display=swap" rel="stylesheet">

<!-- La MISMA hoja de estilos del sitio. Si cambias la marca, esta
     página cambia sola. -->
<link rel="stylesheet" href="{SITIO_URL}/css/styles.css">

<style>
  /* Lo único propio de esta pantalla: centrar todo verticalmente
     y darle al logo su entrada y su latido. */
  .gracias{{
    min-height:100vh;
    min-height:100dvh;
    display:grid;
    place-items:center;
    padding:10vh 6vw;
    text-align:center;
  }}
  .gracias__caja{{ width:min(100%, 34rem); }}

  .gracias__logo{{
    width:88px; margin:0 auto 2rem;
    filter:drop-shadow(0 0 26px rgba(230,185,108,.45));
    animation:aparecer-logo 1.2s var(--curva) both,
              latir-logo 6s ease-in-out 1.2s infinite;
  }}
  @keyframes aparecer-logo{{
    from{{ opacity:0; transform:translateY(12px) scale(.86); }}
    to  {{ opacity:1; transform:none; }}
  }}

  .gracias h1{{ margin-bottom:1.2rem; }}
  .gracias__texto{{ max-width:34ch; margin-inline:auto; }}
  .gracias__texto em{{ color:var(--oro); font-style:italic; }}
  .gracias .btn{{ margin:.5rem .35rem; }}
  .gracias__nota{{
    margin-top:2.5rem;
    font-size:.82rem;
    color:var(--texto-suave);
    max-width:42ch; margin-inline:auto;
  }}
  .gracias__nota a{{ color:var(--oro-claro); }}

  /* El aura dorada detrás del contenido, como en el cierre del sitio.
     Sin overflow:hidden, para que no deje un canto recto. */
  .gracias__aura{{
    position:fixed; left:50%; top:50%;
    width:min(150vw, 1200px); aspect-ratio:1/1;
    transform:translate(-50%,-50%);
    background:radial-gradient(circle,
        rgba(230,185,108,.14) 0%,
        rgba(125,107,174,.10) 32%,
        rgba(125,107,174,.03) 56%,
        transparent 76%);
    pointer-events:none;
    z-index:-1;
    animation:latido 9s ease-in-out infinite alternate;
  }}
</style>
</head>

<body>

<!-- Las mismas tres capas de fondo que index.html.
     cielo.js busca el canvas por su id y lo dibuja solo. -->
<div class="cielo" aria-hidden="true">
  <div class="cielo__nebulosa"></div>
  <canvas id="cielo-estrellas"></canvas>
  <div class="cielo__vineta"></div>
</div>
<div class="gracias__aura" aria-hidden="true"></div>

<main class="gracias">
  <div class="gracias__caja">
    <img class="gracias__logo" src="{SITIO_URL}/assets/eclipse.png"
         alt="Cosmos y Esencia" width="420" height="404">
    <h1>{html.escape(titular)}</h1>
    <p class="gracias__texto">{texto}</p>
    {botones_html}
    <p class="gracias__nota">{nota}</p>
  </div>
</main>

<script src="{SITIO_URL}/js/cielo.js" defer></script>
</body>
</html>"""


def boton(url, etiqueta):
    return (f'<p><a class="btn btn--solid" href="{html.escape(url, quote=True)}">'
            f'{html.escape(etiqueta)}</a></p>')


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
                    f'¿Necesitas ayuda? Escríbenos a '
                    f'<a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a>.'
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
                    f'Si pasan 24 horas y no llega, escríbenos a '
                    f'<a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a> '
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
                    f'Si no llega, escríbenos a '
                    f'<a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a> '
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
                f"Gracias por tu compra de <em>{html.escape(producto['titulo'])}</em>. "
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
                f'¿No llega? Escríbenos a '
                f'<a href="mailto:{CORREO_CONTACTO}">{CORREO_CONTACTO}</a>.'
            ))

    def log_message(self, formato, *args):
        return
