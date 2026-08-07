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

import requests
from supabase import create_client


# ===========================================================================
# 1. CREDENCIALES
# ---------------------------------------------------------------------------
# NUNCA escribas estos valores aquí dentro. Van en dos lugares:
#
#   a) En tu computadora: archivo .env.local en la raíz del proyecto
#      (para probar con "vercel dev"). Ese archivo NO se sube a GitHub.
#
#   b) En producción: Vercel → tu proyecto → Settings → Environment
#      Variables. Ahí pegas cada nombre y su valor, y luego haces
#      "Redeploy" para que la función los tome.
#
# Dónde consigue cada uno:
#   MP_ACCESS_TOKEN     Mercado Pago → Tus integraciones → tu app →
#                       Credenciales de producción → Access Token
#   MP_WEBHOOK_SECRET   Mercado Pago → Webhooks → al configurar la URL
#                       te muestra una "clave secreta". Cópiala.
#   SUPABASE_URL        Supabase → Project Settings → API → Project URL
#   SUPABASE_SERVICE_KEY Supabase → Project Settings → API → service_role
#                       ⚠️ La service_role tiene permisos totales.
#                          Solo vive en el servidor. Jamás en el HTML.
#   RESEND_API_KEY      resend.com → API Keys (para enviar el correo)
# ===========================================================================

MP_ACCESS_TOKEN      = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET    = os.environ.get("MP_WEBHOOK_SECRET", "")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY       = os.environ.get("RESEND_API_KEY", "")
CORREO_REMITENTE     = os.environ.get("CORREO_REMITENTE", "hola@cosmosyesencia.com")

# Nombre del bucket que creaste en Supabase → Storage.
# ⚠️ Debe ser PRIVADO. Si es público, cualquiera con la ruta descarga el PDF
#    sin pagar y las Signed URLs pierden sentido.
BUCKET = "ebooks"

# Cuánto dura el enlace antes de caducar, en segundos.
# 172800 = 48 horas. Suficiente para que el cliente lo abra sin prisa.
DURACION_ENLACE = 60 * 60 * 48


# ===========================================================================
# 2. CATÁLOGO
# ---------------------------------------------------------------------------
# La llave (izquierda) es el "external_reference": el texto que TÚ escribes
# al crear el Link de Pago en Mercado Pago, en el campo "Referencia externa".
# Debe coincidir exactamente, en minúsculas.
#
# "archivos" es la ruta dentro del bucket de Supabase Storage.
# Si subiste el PDF a la raíz del bucket, la ruta es sólo el nombre.
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
    """
    Comprueba que el aviso venga realmente de Mercado Pago.

    Mercado Pago manda dos encabezados:
        x-signature:  ts=1704908010,v1=618c85345248dd820d5fd456...
        x-request-id: un identificador del aviso

    La receta oficial: se arma un texto con este formato exacto
        id:<PAYMENT_ID>;request-id:<REQUEST_ID>;ts:<TS>;
    se firma con HMAC-SHA256 usando tu clave secreta, y el resultado
    debe ser idéntico al v1 que llegó.

    Si no configuraste MP_WEBHOOK_SECRET, dejamos pasar el aviso
    (útil sólo mientras pruebas). En producción, ponla siempre.
    """
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

    # compare_digest evita filtrar información por el tiempo de comparación.
    return hmac.compare_digest(calculada, v1)


def consultar_pago(payment_id):
    """Le pregunta a Mercado Pago los datos completos del pago."""
    respuesta = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
        timeout=10,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def generar_enlaces(rutas):
    """
    Pide a Supabase Storage una Signed URL por cada PDF.

    Una Signed URL es un enlace con una firma y una fecha de caducidad
    incrustadas. Funciona aunque el bucket sea privado, y deja de
    funcionar sola cuando pasa el tiempo que definimos arriba.
    """
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    enlaces = []

    for ruta in rutas:
        resultado = supabase.storage.from_(BUCKET).create_signed_url(
            ruta, DURACION_ENLACE
        )
        # Según la versión de supabase-py la llave viene como
        # "signedURL" o "signedUrl". Aceptamos las dos.
        url = resultado.get("signedURL") or resultado.get("signedUrl")
        if url:
            enlaces.append(url)

    return enlaces


def registrar_venta(supabase_client, datos):
    """
    Guarda la venta en la tabla 'entregas' de Supabase.
    Sirve para reenviar el enlace si al cliente se le venció.

    Crea la tabla una sola vez en Supabase → SQL Editor:

        create table entregas (
          id           bigserial primary key,
          payment_id   text unique not null,
          producto     text not null,
          correo       text,
          monto        numeric,
          creado_en    timestamptz default now()
        );
        alter table entregas enable row level security;
        -- Sin políticas: sólo la service_role (este servidor) puede leerla.
    """
    supabase_client.table("entregas").upsert(
        datos, on_conflict="payment_id"
    ).execute()


def enviar_correo(destinatario, titulo, enlaces):
    """
    Envía el enlace de descarga con Resend (resend.com, plan gratuito
    suficiente para empezar). Si prefieres otro servicio, cambia sólo
    esta función: el resto del flujo no se entera.

    Requisito: verificar tu dominio en Resend para que el correo
    no caiga en spam.
    """
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
# ---------------------------------------------------------------------------
# Vercel busca una clase llamada exactamente "handler".
# El nombre del archivo define la URL: api/webhook.py → /api/webhook
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
        """Para abrir la URL en el navegador y confirmar que está viva."""
        self._responder(200, "Webhook de Cosmos y Esencia activo.")

    def do_POST(self):
        try:
            # --- Leemos el aviso que mandó Mercado Pago ---
            largo = int(self.headers.get("Content-Length", 0))
            crudo = self.rfile.read(largo) if largo else b"{}"
            aviso = json.loads(crudo or b"{}")

            # Mercado Pago manda varios tipos de aviso. Sólo nos interesan
            # los de tipo "payment"; los demás los ignoramos con un 200.
            tipo = aviso.get("type") or aviso.get("topic")
            if tipo != "payment":
                return self._responder(200, "Aviso ignorado (no es un pago).")

            payment_id = str(aviso.get("data", {}).get("id", ""))
            if not payment_id:
                return self._responder(200, "Aviso sin id de pago.")

            # --- Paso 2: ¿de verdad viene de Mercado Pago? ---
            if not firma_valida(self.headers, payment_id):
                print("Firma inválida para el pago", payment_id)
                return self._responder(401, "Firma inválida.")

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
            # Registramos el error pero contestamos 200: así Mercado Pago
            # no reintenta en bucle. Revisa el detalle en Vercel → Logs.
            print("ERROR en el webhook:", repr(error))
            return self._responder(200, "Error registrado.")

    def log_message(self, formato, *args):
        """Silencia el log por defecto; usamos print() donde importa."""
        return
