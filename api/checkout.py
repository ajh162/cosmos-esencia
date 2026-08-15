import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Jalamos tu token de las variables de entorno de Vercel
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")

# Los precios y títulos de tus libros
CATALOGO = {
    "renacer": {
        "title": "Renacer Energético — 21 días",
        "price": 149.0
    },
    "matriz": {
        "title": "Matriz del Destino",
        "price": 149.0
    }
}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Ver qué botón presionó el cliente (renacer o matriz)
        url_parseada = urlparse(self.path)
        parametros = parse_qs(url_parseada.query)
        producto_id = parametros.get("producto", [""])[0].lower()

        if producto_id not in CATALOGO:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Producto no encontrado")
            return

        producto = CATALOGO[producto_id]

        # 2. Armar la orden oficial para Mercado Pago (Preference)
        url = "https://api.mercadopago.com/checkout/preferences"
        headers = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "items": [
                {
                    "title": producto["title"],
                    "quantity": 1,
                    "currency_id": "MXN",
                    "unit_price": producto["price"]
                }
            ],
            # Esta es la magia: conectamos la orden con tu webhook
            "external_reference": producto_id,
            "notification_url": "https://cosmosesencia.vercel.app/api/webhook",
            # A dónde los regresamos después de pagar
            "back_urls": {
                "success": "https://cosmosyesencia.com/",
                "failure": "https://cosmosyesencia.com/",
                "pending": "https://cosmosyesencia.com/"
            },
            "auto_return": "approved"
        }

        try:
            # 3. Pedirle a Mercado Pago que genere el link de cobro
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()
            init_point = data["init_point"] # El link oficial generado

            # 4. Redirigir al cliente instantáneamente a la pantalla de pago
            self.send_response(302)
            self.send_header("Location", init_point)
            self.end_headers()
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error creando pago: {str(e)}".encode())
