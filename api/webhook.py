"""
============================================================================
 COSMOS Y ESENCIA — Webhook de entrega automática
 Ruta pública: https://TU-DOMINIO.vercel.app/api/webhook
============================================================================

 QUÉ HACE ESTE ARCHIVO, EN ORDEN:

   1. Mercado Pago avisa "hubo un movimiento en el pago 12345".
      (El aviso NO trae el monto ni el estado: sólo el ID.)
   2. Verificamos la firma del aviso para asegurarnos de que
      de verdad viene de Mercado Pago y no de un impostor.
   3. Le preguntamos a la API de Mercado Pago: "¿cómo quedó el pago 12345?"
   4. Si el estado es "approved", vemos qué libro compró
      (viene en el campo external_reference del link de pago).
   5. Le pedimos a Supabase Storage una Signed URL: un enlace
      temporal y privado al PDF, que caduca solo.
   6. Guardamos la venta en una tabla de Supabase (para reenviar
      el enlace si el cliente lo pide).
   7. Enviamos el enlace por correo al comprador.
   8. Respondemos 200 a Mercado Pago. Si no respondes 200,
      Mercado Pago reintenta el aviso varias veces.

 IMPORTANTE: siempre respondemos 200, incluso si algo falla por dentro.
 Así evitamos que Mercado Pago reintente en bucle. Los errores quedan
 en los logs de Vercel (Dashboard → tu proyecto → Logs).
============================================================================
"""

import os
import json
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests
from supabase import create_client


# ===========================================================================
# 1. CREDENCIALES
# ---------------------------------------------------------------------------
MP_ACCESS_TOKEN      = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET    = os.environ.get("MP_WEBHOOK_SECRET", "")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY       = os.environ.get("RESEND_API_KEY", "")
CORREO_REMITENTE     = os.environ.get("CORREO_REMITENTE", "hola@cosmosyesencia.com")

BUCKET = "ebooks"
DURACION_ENLACE = 60 * 60 * 48


# ===========================================================================
# 2. CATÁLOGO
# ===========================================================================

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
# 3. FUNCIONES DE APOYO
# ===========================================================================

def firma_valida(headers, payment_id):
    if not MP_WEBHOOK_SECRET:
        print("AVISO: MP_WEBHOOK_SECRET vacío, no se validó la firma.")
        return True

    x_signature = headers.get("x-signature", "")
    x_request_id = headers.get("x-request-id", "")

    ts, v1 = None, None
    for parte in x_signature.split(","):
        if "=" in parte:
            clave, valor = parte.split("=", 1)
            clave = clave.strip()
            if clave == "ts":
                ts = valor.strip()
            elif clave == "v1":
                v1 = valor.strip()

    if not ts or not v1:
        return False

    manifiesto = f"id:{payment_id};request-id:{x_request_id};ts:{ts};"
    calculada = hmac.new(
        MP_WEBHOOK_SECRET.encode(),
        manifiesto.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(calculada, v1)


def consultar_pago(payment_id):
    respuesta = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
        timeout=10,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def generar_enlaces(rutas):
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    enlaces = []

    for ruta in rutas:
        resultado = supabase.storage.from_(BUCKET).create_signed_url(
            ruta, DURACION_ENLACE
        )
        url = resultado.get("signedURL") or resultado.get("signedUrl")
        if url:
            enlaces.append(url)

    return enlaces


def registrar_venta(supabase_client, datos):
    supabase_client.table("entregas").upsert(
        datos, on_conflict="payment_id"
    ).execute()


def enviar_correo(destinatario, titulo, enlaces):
    if not RESEND_API_KEY:
        print("AVISO: RESEND_API_KEY vacío. Enlaces generados:", enlaces)
        return

    botones = "".join(
        f'<p style="margin:18px 0"><a href="{u}" '
        f'style="background:#0D1730;color:#FBFAF8;padding:14px 28px;'
        f'border-radius:999px;text-decoration:none;font-family:Arial,sans-serif;'
        f'font-size:14px;letter-spacing:.12em">DESCARGAR PDF {i}</a></p>'
        for i, u in enumerate(enlaces, start=1)
    )

    html = f"""
    <div style="font-family:Georgia,serif;color:#3E4258;max-width:520px">
      <h1 style="color:#0D1730;font-weight:400">Tu cuaderno está listo</h1>
      <p>Gracias por tu compra de <strong>{titulo}</strong>.</p>
      {botones}
      <p style="font-size:13px;color:#6E7288">
        El enlace es personal y caduca en 48 horas. Descarga el archivo y
        guárdalo en tu dispositivo. Si se venció antes de que lo abrieras,
        responde a este correo y te enviamos uno nuevo.
      </p>
      <p style="font-size:12px;color:#6E7288">Cosmos y Esencia</p>
    </div>
    """

    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": f"Cosmos y Esencia <{CORREO_REMITENTE}>",
            "to": [destinatario],
            "subject": f"Tu descarga: {titulo}",
            "html": html,
        },
        timeout=10,
    )


# ===========================================================================
# 4. LA FUNCIÓN SERVERLESS
# ===========================================================================

class handler(BaseHTTPRequestHandler):

    def _responder(self, codigo, mensaje):
        cuerpo = json.dumps({"mensaje": mensaje}).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._responder(200, "Webhook de Cosmos y Esencia activo.")

    def do_POST(self):
        try:
            # --- Paso 1: Extraer datos del JSON (Webhook) y de la URL (IPN) ---
            largo = int(self.headers.get("Content-Length", 0))
            crudo = self.rfile.read(largo) if largo else b"{}"
            try:
                aviso = json.loads(crudo or b"{}")
            except json.JSONDecodeError:
                aviso = {}

            url_parseada = urlparse(self.path)
            parametros = parse_qs(url_parseada.query)

            # Buscamos el tipo de evento
            tipo = (
                aviso.get("type") or 
                aviso.get("topic") or 
                (parametros.get("topic", [None])[0]) or 
                (parametros.get("type", [None])[0])
            )

            if tipo != "payment":
                return self._responder(200, "Aviso ignorado (no es un pago).")

            # Buscamos el ID del pago
            payment_id = (
                aviso.get("data", {}).get("id") or 
                aviso.get("id") or 
                (parametros.get("id", [""])[0])
            )
            payment_id = str(payment_id).strip()

            if not payment_id:
                return self._responder(200, "Aviso sin id de pago.")


            # --- Paso 3: consultamos el estado real del pago ---
            pago = consultar_pago(payment_id)

            if pago.get("status") != "approved":
                print("Pago", payment_id, "en estado", pago.get("status"))
                return self._responder(200, "Pago aún no aprobado.")

            # --- Paso 4: ¿qué libro compró? ---
            referencia = (pago.get("external_reference") or "").strip().lower()
            producto = CATALOGO.get(referencia)

            if not producto:
                print("Referencia desconocida:", referencia)
                return self._responder(200, "Producto no reconocido.")

            correo = (pago.get("payer") or {}).get("email", "")

            # --- Paso 5: enlaces temporales al PDF ---
            enlaces = generar_enlaces(producto["archivos"])
            if not enlaces:
                print("No se pudo generar la Signed URL para", referencia)
                return self._responder(200, "Error al generar el enlace.")

            # --- Paso 6: dejamos constancia de la venta ---
            supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            registrar_venta(supabase, {
                "payment_id": payment_id,
                "producto": referencia,
                "correo": correo,
                "monto": pago.get("transaction_amount"),
            })

            # --- Paso 7: se lo mandamos al cliente ---
            if correo:
                enviar_correo(correo, producto["titulo"], enlaces)
            else:
                print("Pago", payment_id, "sin correo del comprador.")

            print("Entrega completada:", referencia, "→", correo)
            return self._responder(200, "Entrega completada.")

        except Exception as error:
            print("ERROR en el webhook:", repr(error))
            return self._responder(200, "Error registrado.")

    def log_message(self, formato, *args):
        return
