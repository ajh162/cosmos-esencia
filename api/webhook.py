"""
============================================================================
 COSMOS Y ESENCIA — Webhook de entrega automática
 Ruta pública: https://www.cosmosyesencia.com/api/webhook
============================================================================

 QUÉ HACE ESTE ARCHIVO, EN ORDEN:

   1. Mercado Pago avisa "hubo un movimiento en el pago 12345".
      (El aviso NO trae el monto ni el estado: sólo el ID.)
   2. Verificamos la firma del aviso para asegurarnos de que
      de verdad viene de Mercado Pago y no de un impostor.
   3. Le preguntamos a la API de Mercado Pago: "¿cómo quedó el pago 12345?"
   4. Si el estado es "approved", vemos qué libro compró.
   5. Le pedimos a Supabase Storage una Signed URL: un enlace
      temporal y privado al PDF, que caduca solo.
   6. Guardamos la venta en la tabla "entregas".
   7. Enviamos el enlace por correo al comprador.
   8. Respondemos 200 a Mercado Pago siempre, incluso si algo falla
      por dentro, para que no reintente en bucle. Los errores quedan
      en los logs de Vercel (Dashboard → tu proyecto → Logs).

 ── CAMBIOS DE ESTA VERSIÓN ────────────────────────────────────────────────
   • El correo ahora lleva reply_to apuntando a CORREO_CONTACTO.
     Sale desde el dominio verificado en Resend (que es lo que garantiza
     la entregabilidad), pero cuando el comprador presiona "Responder",
     su mensaje se va al Gmail del negocio.

     POR QUÉ IMPORTA: el dominio tiene un registro MX solo en el host
     "send", que es el que Resend usa para ENVIAR. El dominio raíz no
     tiene MX, así que hola@cosmosyesencia.com no puede RECIBIR nada.
     Sin reply_to, las respuestas de los clientes rebotan y se pierden.

 ── CAMBIOS DE LA VERSIÓN ANTERIOR ─────────────────────────────────────────
   • El paso 2 AHORA SÍ SE EJECUTA. La función firma_valida() ya existía
     y estaba bien escrita, pero nunca se llamaba desde do_POST().
   • La venta se registra ANTES de intentar el correo. Antes, si Resend
     fallaba, no quedaba rastro de la venta en ningún lado.
   • Si el pago no trae correo del comprador (pasa con OXXO, transferencia
     o pagos como invitado), la venta se guarda con entregado = false
     para que puedas encontrarla y reenviar el enlace a mano.
   • Un solo cliente de Supabase por invocación, en vez de dos.
============================================================================

 TABLA QUE NECESITA ESTE ARCHIVO
 (Es la que ya está creada en Supabase. Se deja aquí por si algún día
  hay que recrearla desde cero.)

   create table if not exists entregas (
     id          bigserial primary key,
     payment_id  text unique not null,
     producto    text not null,
     correo      text,
     monto       numeric,
     creado_en   timestamptz default now()
   );

   alter table entregas add column if not exists entregado boolean default false;
   alter table entregas enable row level security;

 El upsert de más abajo usa on_conflict="payment_id", que funciona igual
 con un UNIQUE que con una llave primaria.

 RLS activado y SIN políticas es lo correcto: nadie puede leer la tabla
 desde el navegador, y este archivo sí puede escribir porque usa la llave
 service_role, que se salta el RLS por diseño.
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
# ===========================================================================

MP_ACCESS_TOKEN      = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET    = os.environ.get("MP_WEBHOOK_SECRET", "")
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY       = os.environ.get("RESEND_API_KEY", "")

# Desde dónde SALE el correo. Tiene que ser el dominio verificado en Resend.
CORREO_REMITENTE     = os.environ.get("CORREO_REMITENTE", "hola@cosmosyesencia.com")

# A dónde LLEGAN las respuestas de los compradores. Aquí sí puede ir un
# Gmail: no se usa para enviar, solo como destino del botón "Responder".
CORREO_CONTACTO      = os.environ.get("CORREO_CONTACTO", "").strip()

# La dirección del sitio. Se usa para traer el logo al correo: las imágenes
# de un correo tienen que apuntar a una dirección pública y absoluta.
SITIO_URL            = os.environ.get("SITIO_URL", "https://www.cosmosyesencia.com").rstrip("/")

BUCKET = "ebooks"
DURACION_ENLACE = 60 * 60 * 24  # 24 horas


# ===========================================================================
# 2. CATÁLOGO
# ---------------------------------------------------------------------------
# Las claves deben ser IDÉNTICAS a las de checkout.py.
# Los nombres de archivo deben ser IDÉNTICOS a los del bucket de Supabase
# (respetando mayúsculas, guiones y la extensión).
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
    Comprueba que el aviso venga de verdad de Mercado Pago.

    Mercado Pago manda dos encabezados:
      x-signature:  ts=1704908010,v1=618c85345248dd820d5fd4...
      x-request-id: un identificador del aviso

    Con esos datos y tu clave secreta se arma un texto ("manifiesto"),
    se le saca una firma HMAC-SHA256 y se compara con la v1 que llegó.
    Si coinciden, el aviso es auténtico.

    OJO: si MP_WEBHOOK_SECRET está vacío, esta función deja pasar todo
    y lo avisa en los logs. Eso es a propósito, para que puedas hacer
    pruebas locales sin la clave. En producción la clave SIEMPRE debe
    estar puesta.
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

    # compare_digest en vez de == : evita que se pueda adivinar la firma
    # midiendo cuánto tarda la comparación.
    return hmac.compare_digest(calculada, v1)


def consultar_pago(payment_id):
    """Le pregunta a Mercado Pago el estado real del pago."""
    respuesta = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
        timeout=10,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def cliente_supabase():
    """Un solo cliente por invocación, reutilizado por todas las funciones."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def generar_enlaces(supabase, rutas):
    """Convierte los nombres de archivo en enlaces temporales de descarga."""
    enlaces = []
    for ruta in rutas:
        resultado = supabase.storage.from_(BUCKET).create_signed_url(
            ruta, DURACION_ENLACE
        )
        url = resultado.get("signedURL") or resultado.get("signedUrl")
        if url:
            enlaces.append(url)
    return enlaces


def registrar_venta(supabase, datos):
    """
    Guarda la venta. upsert con on_conflict="payment_id" significa:
    si Mercado Pago manda el mismo aviso dos veces, se actualiza el
    registro en lugar de crear uno duplicado.
    """
    supabase.table("entregas").upsert(datos, on_conflict="payment_id").execute()


def enviar_correo(destinatario, titulo, enlaces):
    """Manda el correo con los botones de descarga. Devuelve True si salió.

    SOBRE EL DISEÑO DEL CORREO
    -----------------------------------------------------------------------
    Está armado con tablas y estilos escritos en cada etiqueta. Se ve
    anticuado por dentro, pero es la única forma de que se vea igual en
    Gmail, Outlook y Apple Mail: los clientes de correo ignoran las hojas de
    estilo externas y varios ni siquiera soportan flexbox.

    Tampoco se pueden usar las tipografías del sitio. Cormorant Garamond no
    carga en correo, así que va Georgia: serif también, y la trae cualquier
    equipo. El resultado se siente de la misma familia.

    Los colores son los del manual de marca: noche #131A29, superficie
    #232F4C, oro #E6B96C, lavanda #B9A8D6 y marfil #F7F3EE.
    """
    if not RESEND_API_KEY:
        print("AVISO: RESEND_API_KEY vacío. Enlaces generados:", enlaces)
        return False

    # --- Botones de descarga ---
    # Van armados con tabla porque Outlook ignora el padding de un enlace
    # suelto y el botón se ve como texto plano.
    total = len(enlaces)
    botones = ""
    for i, u in enumerate(enlaces, start=1):
        etiqueta = "Descargar tu cuaderno" if total == 1 else f"Descargar cuaderno {i}"
        botones += f"""
            <table role="presentation" cellpadding="0" cellspacing="0"
                   style="margin:0 auto 12px">
              <tr>
                <td align="center" bgcolor="#E6B96C" style="border-radius:999px">
                  <a href="{u}"
                     style="display:inline-block;padding:15px 34px;
                            font-family:Georgia,'Times New Roman',serif;
                            font-size:15px;letter-spacing:.14em;
                            text-transform:uppercase;color:#131A29;
                            text-decoration:none">{etiqueta}</a>
                </td>
              </tr>
            </table>"""

    html = f"""<!DOCTYPE html>
<html lang="es-MX">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tu cuaderno de Cosmos y Esencia</title>
</head>
<body style="margin:0;padding:0;background:#0B111D">

<!-- Línea de vista previa: lo que se lee en la bandeja antes de abrir -->
<div style="display:none;max-height:0;overflow:hidden;opacity:0">
  Tu descarga de {titulo} ya está lista.
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       bgcolor="#0B111D" style="background:#0B111D">
  <tr>
    <td align="center" style="padding:28px 12px">

      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:600px">

        <!-- ===================== CABECERA ===================== -->
        <tr>
          <td align="center" bgcolor="#131A29"
              style="background:#131A29;border-radius:16px 16px 0 0;
                     padding:40px 28px 34px">
            <img src="{SITIO_URL}/assets/logo-completo.png"
                 alt="Cosmos y Esencia" width="190"
                 style="display:block;width:190px;max-width:66%;height:auto;border:0">
            <div style="font-family:Georgia,'Times New Roman',serif;font-size:11px;
                        letter-spacing:.32em;text-transform:uppercase;
                        color:#E6B96C;padding-top:24px">Tu descarga está lista</div>
            <div style="font-family:Georgia,'Times New Roman',serif;font-size:28px;
                        color:#F7F3EE;padding-top:10px;line-height:1.3">
              Tu cuaderno te espera
            </div>
          </td>
        </tr>

        <!-- Hilo dorado que separa la cabecera del cuerpo -->
        <tr>
          <td bgcolor="#E6B96C" style="background:#E6B96C;height:2px;
                                       line-height:2px;font-size:0">&nbsp;</td>
        </tr>

        <!-- ===================== CUERPO ===================== -->
        <tr>
          <td bgcolor="#232F4C" style="background:#232F4C;padding:34px 30px 30px">

            <p style="margin:0 0 26px;font-family:Georgia,'Times New Roman',serif;
                      font-size:17px;line-height:1.7;color:#F7F3EE;text-align:center">
              Gracias por tu compra de<br>
              <span style="color:#E6B96C">{titulo}</span>
            </p>

            {botones}

            <p style="margin:24px 0 0;font-family:Arial,Helvetica,sans-serif;
                      font-size:13px;line-height:1.7;color:#B9A8D6;text-align:center">
              El enlace es personal y caduca en 24 horas. Descarga el archivo y
              guárdalo en tu dispositivo. Si se venció antes de que lo abrieras,
              responde a este correo y te enviamos uno nuevo.
            </p>

          </td>
        </tr>

        <!-- ===================== PIE ===================== -->
        <tr>
          <td bgcolor="#131A29" align="center"
              style="background:#131A29;border-radius:0 0 16px 16px;
                     padding:26px 30px 30px">
            <div style="font-family:Georgia,'Times New Roman',serif;font-size:13px;
                        letter-spacing:.28em;text-transform:uppercase;color:#E6B96C">
              Cosmos y Esencia
            </div>
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;
                        line-height:1.7;color:#7D6BAE;padding-top:10px">
              Energía, astrología y conexión interior
            </div>
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>
</body>
</html>"""

    # Versión en texto plano. Mejora la entregabilidad (los filtros desconfían
    # de los correos que solo traen HTML) y sirve para quien lee sin formato.
    texto = "COSMOS Y ESENCIA\n\nTu cuaderno te espera.\n\n"
    texto += f"Gracias por tu compra de {titulo}.\n\n"
    for i, u in enumerate(enlaces, start=1):
        etiqueta = "Descarga" if total == 1 else f"Descarga {i}"
        texto += f"- {etiqueta}: {u}\n"
    texto += "\nEl enlace es personal y caduca en 24 horas.\n"
    texto += "Si se vencio, responde a este correo y te enviamos uno nuevo.\n"

    cuerpo = {
        "from": f"Cosmos y Esencia <{CORREO_REMITENTE}>",
        "to": [destinatario],
        "subject": f"Tu descarga: {titulo}",
        "html": html,
        "text": texto,
    }

    # A dónde va el mensaje cuando el comprador presiona "Responder".
    # Solo se agrega si la variable existe: un reply_to vacío hace que
    # Resend rechace el envío.
    if CORREO_CONTACTO:
        cuerpo["reply_to"] = CORREO_CONTACTO
    else:
        print("AVISO: CORREO_CONTACTO vacío. Las respuestas de los compradores",
              "irán al remitente, que no tiene MX en el dominio raíz y por lo",
              "tanto no recibe correo.")

    respuesta = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=cuerpo,
        timeout=10,
    )

    if respuesta.status_code >= 300:
        # Causa típica: el dominio no está verificado en Resend.
        print("ERROR de Resend:", respuesta.status_code, respuesta.text[:300])
        return False

    return True


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
        # Sirve para probar desde el navegador que la función está viva.
        self._responder(200, "Webhook de Cosmos y Esencia activo.")

    def do_POST(self):
        try:
            # --- Paso 1: leer el aviso (llega como JSON o como query) ---
            largo = int(self.headers.get("Content-Length", 0))
            crudo = self.rfile.read(largo) if largo else b"{}"
            try:
                aviso = json.loads(crudo or b"{}")
            except json.JSONDecodeError:
                aviso = {}

            parametros = parse_qs(urlparse(self.path).query)

            tipo = (
                aviso.get("type")
                or aviso.get("topic")
                or parametros.get("topic", [None])[0]
                or parametros.get("type", [None])[0]
            )

            if tipo != "payment":
                return self._responder(200, "Aviso ignorado (no es un pago).")

            payment_id = (
                aviso.get("data", {}).get("id")
                or aviso.get("id")
                or parametros.get("id", [""])[0]
            )
            payment_id = str(payment_id).strip()

            if not payment_id:
                return self._responder(200, "Aviso sin id de pago.")

            # --- Paso 2: verificar que el aviso sea auténtico ---
            # ESTA LLAMADA ES LA QUE FALTABA. Sin ella, cualquiera podía
            # mandar un POST a esta URL y disparar el proceso de entrega.
            if not firma_valida(self.headers, payment_id):
                print("FIRMA INVÁLIDA para el pago", payment_id, "— aviso descartado.")
                return self._responder(200, "Firma inválida.")

            # --- Paso 3: consultar el estado real del pago ---
            pago = consultar_pago(payment_id)
            estado = pago.get("status")

            if estado != "approved":
                # Normal en OXXO o transferencia: el pago tarda en acreditarse.
                # Mercado Pago volverá a avisar cuando cambie de estado.
                print("Pago", payment_id, "en estado", estado)
                return self._responder(200, "Pago aún no aprobado.")

            # --- Paso 4: ¿qué libro compró? ---
            referencia = (pago.get("external_reference") or "").strip().lower()
            producto = CATALOGO.get(referencia)

            if not producto:
                print("Referencia desconocida:", referencia, "en pago", payment_id)
                return self._responder(200, "Producto no reconocido.")

            correo = (pago.get("payer") or {}).get("email", "") or ""
            correo = correo.strip()

            supabase = cliente_supabase()

            # --- Paso 5: registrar la venta ANTES de intentar entregarla ---
            # Si el correo falla después, la venta ya quedó guardada y la
            # puedes rescatar. Antes, un fallo de Resend borraba el rastro.
            registrar_venta(supabase, {
                "payment_id": payment_id,
                "producto": referencia,
                "correo": correo,
                "monto": pago.get("transaction_amount"),
                "entregado": False,
            })

            # --- Paso 6: enlaces temporales al PDF ---
            enlaces = generar_enlaces(supabase, producto["archivos"])
            if not enlaces:
                print("No se pudo generar la Signed URL para", referencia,
                      "— revisa que el nombre del archivo en CATALOGO",
                      "sea idéntico al del bucket de Supabase.")
                return self._responder(200, "Error al generar el enlace.")

            # --- Paso 7: mandarlo por correo ---
            if not correo:
                # Pasa con pagos en efectivo, transferencia o como invitado.
                # La venta queda con entregado = false: búscala en Supabase
                # y reenvía el enlace a mano. El comprador de todos modos
                # ve su descarga en /api/gracias al volver del pago.
                print("SIN CORREO — pago", payment_id, "producto", referencia,
                      "— entrega manual pendiente.")
                return self._responder(200, "Venta registrada sin correo.")

            entregado = enviar_correo(correo, producto["titulo"], enlaces)

            # --- Paso 8: dejar constancia de si el correo salió o no ---
            registrar_venta(supabase, {
                "payment_id": payment_id,
                "producto": referencia,
                "correo": correo,
                "monto": pago.get("transaction_amount"),
                "entregado": entregado,
            })

            print("Entrega", "completada" if entregado else "PENDIENTE",
                  ":", referencia, "→", correo)
            return self._responder(200, "Aviso procesado.")

        except Exception as error:
            print("ERROR en el webhook:", repr(error))
            return self._responder(200, "Error registrado.")

    def log_message(self, formato, *args):
        return
