"""
============================================================================
 COSMOS Y ESENCIA — Creación de la orden de pago
 Ruta pública: https://www.cosmosyesencia.com/api/checkout?producto=renacer
============================================================================

 QUÉ HACE ESTE ARCHIVO:

   1. Lee qué producto quiere el comprador (?producto=renacer).
   2. Le pide a Mercado Pago que genere una orden de cobro (Preference).
   3. Redirige al comprador a la pantalla de pago de Mercado Pago.

 ── CAMBIOS DE ESTA VERSIÓN ────────────────────────────────────────────────
   • El dominio ya NO está escrito a mano en tres lugares distintos.
     Ahora sale de la variable SITIO_URL. Antes decía "cosmosesencia"
     (sin la "y") y por eso Mercado Pago avisaba a una dirección que
     no existe: el cliente pagaba y nunca le llegaba su PDF.
   • Se agregó el producto "paquete", que ya existía en webhook.py
     pero faltaba aquí.
   • Al terminar el pago, el comprador ahora regresa a /api/gracias,
     donde ve su enlace de descarga en pantalla (no solo por correo).
============================================================================
"""

import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ===========================================================================
# 1. CONFIGURACIÓN
# ---------------------------------------------------------------------------
# SITIO_URL es el único lugar donde vive tu dominio. Si algún día cambia,
# lo cambias en Vercel → Settings → Environment Variables y listo.
# OJO: sin diagonal al final.
# ===========================================================================

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
SITIO_URL = os.environ.get("SITIO_URL", "https://www.cosmosyesencia.com").rstrip("/")


# ===========================================================================
# 2. CATÁLOGO
# ---------------------------------------------------------------------------
# Las claves ("renacer", "matriz", "paquete") tienen que ser EXACTAMENTE
# las mismas que están en el CATALOGO de webhook.py. Si aquí dice "paquete"
# y allá dice "combo", la entrega automática falla.
# ===========================================================================

CATALOGO = {
    "renacer": {
        "title": "Renacer Energético — 21 días",
        "price": 5.0,
    },
    "matriz": {
        "title": "Matriz del Destino",
        "price": 149.0,
    },
    "paquete": {
        "title": "Renacer Energético + Matriz del Destino",
        "price": 249.0,
    },
}


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # --- 1. ¿Qué botón presionó el comprador? ---
        url_parseada = urlparse(self.path)
        parametros = parse_qs(url_parseada.query)
        producto_id = parametros.get("producto", [""])[0].strip().lower()

        if producto_id not in CATALOGO:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Producto no encontrado".encode("utf-8"))
            return

        producto = CATALOGO[producto_id]

        # --- 2. Armar la orden para Mercado Pago ---
        payload = {
            "items": [
                {
                    "title": producto["title"],
                    "quantity": 1,
                    "currency_id": "MXN",
                    "unit_price": producto["price"],
                }
            ],
            # external_reference es lo que el webhook lee para saber
            # qué PDF entregar. Tiene que ser la clave del CATALOGO.
            "external_reference": producto_id,

            # A dónde avisa Mercado Pago cuando el pago cambia de estado.
            "notification_url": f"{SITIO_URL}/api/webhook",

            # A dónde regresa el comprador después de pagar.
            # success y pending van a /api/gracias para que vea su enlace
            # en pantalla aunque el correo tarde o caiga en spam.
            "back_urls": {
                "success": f"{SITIO_URL}/api/gracias",
                "pending": f"{SITIO_URL}/api/gracias",
                "failure": f"{SITIO_URL}/",
            },
            "auto_return": "approved",
        }

        headers = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        try:
            # --- 3. Pedirle a Mercado Pago el link de cobro ---
            res = requests.post(
                "https://api.mercadopago.com/checkout/preferences",
                headers=headers,
                json=payload,
                timeout=10,
            )
            res.raise_for_status()
            init_point = res.json()["init_point"]

            # --- 4. Mandar al comprador a la pantalla de pago ---
            self.send_response(302)
            self.send_header("Location", init_point)
            self.end_headers()

        except Exception as error:
            # El detalle técnico va a los logs de Vercel, no a la pantalla
            # del comprador: ahí solo verá un mensaje entendible.
            print("ERROR creando la orden de pago:", repr(error))
            self.send_response(302)
            self.send_header("Location", f"{SITIO_URL}/?error=pago")
            self.end_headers()

    def log_message(self, formato, *args):
        return
