"""
============================================================================
 COSMOS Y ESENCIA — Latido para mantener despierta la base de datos
 Ruta pública: https://www.cosmosyesencia.com/api/keepalive
============================================================================

 POR QUÉ EXISTE ESTE ARCHIVO:

   Supabase pausa los proyectos del plan gratuito después de 7 días
   sin actividad. Y "actividad" significa consultas a la base de datos,
   NO visitas al sitio: tu index.html lo sirve Vercel, así que aunque
   entren mil personas a la landing, Supabase no se entera de ninguna.

   Si el proyecto se pausa, pasa lo peor que puede pasar en una tienda:
   alguien paga, el webhook intenta generar su enlace, Supabase responde
   que está dormido, y el comprador se queda sin su PDF.

   Este archivo hace una consulta mínima a la tabla "entregas" una vez
   al día. Eso reinicia el contador de los 7 días.

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
   de esa hora. Para lo que necesitamos, sobra.

 SEGURIDAD:

   Esta ruta es pública, así que cualquiera podría llamarla. Por eso
   pide un encabezado Authorization con la clave CRON_SECRET, que
   Vercel envía automáticamente en sus llamadas programadas.

   Agrega CRON_SECRET en Vercel → Settings → Environment Variables
   si todavía no aparece. Un valor largo y al azar sirve; puedes
   generarlo con:  python -c "import secrets; print(secrets.token_hex(32))"
============================================================================
"""

import os
import json
import hmac
from http.server import BaseHTTPRequestHandler

from supabase import create_client


SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
CRON_SECRET          = os.environ.get("CRON_SECRET", "")


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

        # --- 2. El latido: una consulta mínima a la base ---
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

            # Pedimos una sola columna de un solo renglón. Es la consulta
            # más barata posible que Supabase cuenta como actividad real.
            supabase.table("entregas").select("payment_id").limit(1).execute()

            print("Latido correcto: Supabase respondió.")
            return self._responder(200, {"estado": "despierta"})

        except Exception as error:
            # Si esto aparece varios días seguidos en los logs de Vercel,
            # revísalo: significa que el latido no está llegando y el
            # proyecto puede pausarse.
            print("ERROR en el latido:", repr(error))
            return self._responder(500, {"estado": "sin respuesta"})

    def log_message(self, formato, *args):
        return