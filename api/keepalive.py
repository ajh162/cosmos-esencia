"""
============================================================================
 COSMOS Y ESENCIA — Latido para mantener despierta la base de datos
 Ruta pública: https://www.cosmosyesencia.com/api/keepalive
============================================================================

 POR QUÉ EXISTE ESTE ARCHIVO:

   Supabase pausa los proyectos del plan gratuito cuando no reciben
   suficiente actividad de base de datos durante una semana. Y "actividad"
   significa consultas a la base, NO visitas al sitio: tu index.html lo
   sirve Vercel, así que aunque entren mil personas a la landing, Supabase
   no se entera de ninguna.

   Si el proyecto se pausa, pasa lo peor que puede pasar en una tienda:
   alguien paga, el webhook intenta generar su enlace, Supabase responde
   que está dormido, y el comprador se queda sin su PDF.

 QUÉ CAMBIÓ EN ESTA VERSIÓN:

   La versión anterior solo LEÍA un renglón de la tabla "entregas". El cron
   corría bien todos los días y aun así llegó el aviso de pausa: Supabase
   pide "suficiente" actividad, y una lectura diaria sobre una tabla casi
   vacía aparentemente no alcanza. El umbral exacto no lo publican.

   Ahora el latido ESCRIBE, que es actividad de base sin discusión:

     1. Inserta un renglón en la tabla "latidos"
     2. Borra los latidos de más de 7 días (otra escritura, y de paso
        mantiene la tabla del tamaño de un pañuelo)
     3. Lee la tabla de entregas, como antes

   Además deja el resultado escrito en los registros de Vercel. Antes no:
   Vercel guarda la línea de acceso (el "200 OK") pero no el cuerpo de la
   respuesta, así que el cron podía verse en verde durante meses aunque la
   consulta estuviera fallando en silencio.

 ANTES DE DESPLEGAR — crear la tabla en Supabase (SQL Editor):

     create table if not exists latidos (
       id        bigserial primary key,
       origen    text,
       creado_en timestamptz default now()
     );
     alter table latidos enable row level security;

 CÓMO SE PROGRAMA:

   En vercel.json, en la raíz del proyecto:

     {
       "crons": [
         { "path": "/api/keepalive", "schedule": "0 9 * * *" }
       ]
     }

   0 9 * * *  = todos los días a las 9:00 UTC (3:00 AM en CDMX).
   Vercel solo acepta UTC. En el plan Hobby, el cron corre una vez
   al día como máximo y puede dispararse en cualquier momento dentro
   de esa hora.

 SEGURIDAD:

   Esta ruta es pública, así que cualquiera podría llamarla. Por eso
   pide un encabezado Authorization con la clave CRON_SECRET, que
   Vercel envía automáticamente en sus llamadas programadas.
============================================================================
"""

import os
import json
import hmac
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

from supabase import create_client


SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
CRON_SECRET          = os.environ.get("CRON_SECRET", "")

# Cuántos días de latidos se conservan antes de borrarlos
DIAS_DE_HISTORIAL = 7


class handler(BaseHTTPRequestHandler):

    def _responder(self, codigo, datos):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        # --- 1. ¿Quién está llamando? ---
        # compare_digest en vez de == para no filtrar la clave por el
        # tiempo que tarda la comparación.
        if CRON_SECRET:
            recibido = self.headers.get("Authorization", "")
            esperado = f"Bearer {CRON_SECRET}"
            if not hmac.compare_digest(recibido, esperado):
                return self._responder(401, {"error": "No autorizado"})
        else:
            print("AVISO: CRON_SECRET vacío. La ruta está abierta a cualquiera.")

        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            print("ERROR: faltan las variables de Supabase en el servidor.",
                  "¿Están cargadas en Vercel para Production?")
            return self._responder(500, {"estado": "sin credenciales"})

        # --- 2. El latido ---
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

            # 2.1 Escritura: dejar constancia del latido.
            # Esta es la parte que de verdad cuenta como actividad.
            supabase.table("latidos").insert({"origen": "vercel-cron"}).execute()

            # 2.2 Limpieza: borrar los latidos viejos.
            # Otra escritura, y evita que la tabla crezca sin control.
            # El cliente de Supabase arma la consulta y codifica la fecha por
            # su cuenta, así que no hay que preocuparse por el "+00:00".
            corte = (datetime.now(timezone.utc)
                     - timedelta(days=DIAS_DE_HISTORIAL)).isoformat()
            supabase.table("latidos").delete().lt("creado_en", corte).execute()

            # 2.3 Lectura: la consulta de siempre sobre entregas.
            supabase.table("entregas").select("payment_id").limit(1).execute()

            print("Latido correcto: insercion, limpieza y lectura en orden.")
            return self._responder(200, {"estado": "despierta"})

        except Exception as error:
            # Si esto aparece varios días seguidos en los logs de Vercel,
            # revísalo: significa que el latido no está llegando y el
            # proyecto puede pausarse.
            #
            # Error típico la primera vez: la tabla "latidos" todavía no
            # existe. Créala con el SQL que está al inicio de este archivo.
            print("ERROR en el latido:", repr(error))
            return self._responder(500, {"estado": "sin respuesta"})

    def log_message(self, formato, *args):
        return
