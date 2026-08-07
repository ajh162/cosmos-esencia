# Cosmos y Esencia — landing + entrega automática

Sitio de una sola página para vender dos ebooks, con entrega automática
del PDF cuando Mercado Pago confirma el pago.

- **Front-end:** HTML5 + CSS3 + JavaScript puro. Sin React, sin Next, sin build.
- **Back-end:** una función de Python en Vercel (`/api/webhook`).
- **Archivos:** Supabase Storage (bucket privado + Signed URLs temporales).

---

## 1. Estructura de carpetas

Crea esta carpeta en tu computadora tal cual. Los nombres importan:
Vercel decide las rutas a partir de ellos.

```
cosmos-y-esencia/
│
├── index.html            ← la página (Vercel la sirve en la raíz "/")
├── styles.css
├── script.js
│
├── assets/
│   ├── portada.jpg       ← el banner del cielo nocturno
│   ├── cover-renacer.jpg
│   └── cover-matriz.jpg
│
├── api/                  ← TODO lo que va aquí se vuelve una URL
│   └── webhook.py        ← se publica como  /api/webhook
│
├── requirements.txt      ← librerías de Python que Vercel instalará
├── .env.example          ← plantilla; cópiala a .env.local
└── .gitignore
```

Reglas que conviene tener claras:

- Cualquier `.py` dentro de `/api` se convierte automáticamente en un
  endpoint. `api/webhook.py` → `https://tu-dominio.vercel.app/api/webhook`.
- Dentro de ese archivo, la clase **debe** llamarse `handler`.
- Todo lo que está fuera de `/api` se publica como archivo estático.
- Los PDFs **no** van en este proyecto. Viven en Supabase Storage.
  Si los subes aquí, cualquiera los descarga gratis.

---

## 2. Antes de subir nada

### a) Supabase

1. Crea un proyecto en supabase.com.
2. **Storage → New bucket** → nombre `ebooks` → deja **Public** apagado.
3. Sube tus dos PDFs a ese bucket.
4. Anota los nombres exactos de los archivos y ponlos en el
   diccionario `CATALOGO` dentro de `api/webhook.py`.
5. **SQL Editor** → pega la tabla `entregas` que viene comentada en
   `webhook.py` (función `registrar_venta`) y ejecútala.
6. **Project Settings → API** → copia `Project URL` y la llave
   `service_role`.

### b) Mercado Pago

1. Crea un **Link de pago** por cada producto (tres, si vas a vender
   también el paquete).
2. En cada link, llena el campo **Referencia externa** con exactamente:
   `renacer`, `matriz` o `paquete`. Ese texto es lo que el webhook lee
   para saber qué PDF mandar.
3. Copia cada link y pégalo en el `href="#"` del botón correspondiente
   en `index.html` (búscalos: están marcados con ✏️).
4. **Tus integraciones → tu app → Webhooks**: registra la URL
   `https://tu-dominio.vercel.app/api/webhook` y marca el evento
   **Pagos**. Guarda la clave secreta que te muestra.

### c) Variables de entorno

Copia `.env.example` a `.env.local` y llena los valores. Ese archivo
se queda en tu máquina; no se sube a GitHub.

---

## 3. Subir a Vercel

```bash
npm i -g vercel        # una sola vez
cd cosmos-y-esencia
vercel dev             # prueba local en http://localhost:3000
vercel --prod          # publica
```

Después del primer deploy: **Vercel → tu proyecto → Settings →
Environment Variables**. Pega ahí los mismos nombres del `.env.local`
y vuelve a hacer **Redeploy** para que la función los tome.

---

## 4. Probar que funciona

1. Abre `https://tu-dominio.vercel.app/api/webhook` en el navegador.
   Debe responder `{"mensaje": "Webhook de Cosmos y Esencia activo."}`.
2. Haz una compra real de bajo monto (o usa el modo de prueba de
   Mercado Pago con tus credenciales de test).
3. Revisa **Vercel → Logs**. Deberías ver `Entrega completada: renacer → correo`.
4. Revisa tu bandeja de entrada.

Si algo falla, el error queda impreso en los Logs con el prefijo
`ERROR en el webhook:`.

---

## 5. Qué te falta poner (busca ✏️ en el código)

- Los tres links de pago en `index.html`.
- Los precios reales (`$149`, `$249`) en `index.html`.
- Tu correo de contacto en el pie de `index.html`.
- Los nombres reales de tus PDFs en `CATALOGO`, en `api/webhook.py`.
- Tu dominio verificado en Resend para que los correos no caigan en spam.
