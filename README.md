# Componentes PC · Reserva temporal y código QR

Proyecto final del segundo parcial · CBTIS 272 · Aplicaciones Web (5.º semestre)

**Integrantes:** _(escribir nombres completos de todos los integrantes)_
**Grupo / Plantel:** _(completar)_
**Enlace en Render:** _(pegar https://…onrender.com)_

## Problema que resuelve
Tienda de componentes de PC (Flask + MongoDB Atlas) del primer parcial. Algunas piezas, como las tarjetas gráficas, tienen
pocas unidades. Ahora una persona puede **apartar** unidades durante unos minutos mientras decide, sin que otra persona
se las lleve, y recibe un **comprobante con código QR** que abre su reserva desde el celular.

## Elemento reservado (modelo «Cantidad»)
Cada producto tiene `existencias` (unidades libres). Reservar descuenta unidades; cancelar o vencer las devuelve.

| Concepto | Detalle |
|---|---|
| Duración | 5 minutos (configurable de 3 a 5 con `RESERVA_MINUTOS`) |
| Máximo por reserva | 5 unidades y nunca más que las existencias |
| Quién reserva | La sesión del navegador (ventana normal e incógnito = personas distintas) |
| Colección | `reservas`: `folio`, `recurso_id`, `recurso_nombre`, `visitante_id`, `cantidad`, `estado`, `creada_en`, `expira_en`, `cerrada_en` |
| Estados | `temporal` → `confirmada` · `cancelada` · `vencida` |

### Cómo se evita la doble reserva
El descuento se hace con **una sola operación atómica** de MongoDB:
`update_one({_id, estado: "Disponible", existencias: {$gte: cantidad}}, {$inc: {existencias: -cantidad}})`.
Si dos personas piden la última unidad al mismo tiempo, solo una operación modifica el documento; la otra recibe
«No hay unidades disponibles». Después se guarda la reserva con su `expira_en` en Atlas.

### Qué pasa al vencer
`expira_en` se guarda en Atlas. El contador de la pantalla solo informa: el servidor decide. Las reservas vencidas se
liberan (a) cuando alguien consulta producto, reserva o API, y (b) cada 20 s por un proceso interno. Cada reserva cambia
de `temporal` a `vencida` con `find_one_and_update`, así que las unidades se devuelven **una sola vez**.
Cerrar la pestaña no deja el producto bloqueado.

## Código QR
El QR contiene la dirección **`https://<tu-app>.onrender.com/reserva/<FOLIO>`**, el comprobante público (nombre del
producto, cantidad, estado, tiempo). No contiene datos personales ni secretos. Si el estado cambia (temporal →
confirmada/vencida) el **mismo QR** muestra la información nueva. Se genera con la librería `segno` en `/qr/<FOLIO>.png`
(botón «Descargar QR» en el comprobante).

La base del QR sale de la URL con que se abre la app; si necesitas fijarla, define `APP_BASE_URL`.
Con `localhost` la página lo advierte: ese QR no abre desde un celular.

## Rutas nuevas
| Ruta | Función |
|---|---|
| `POST /reservar/<id>` | Crea la reserva temporal |
| `GET /reserva/<folio>` | Comprobante público (destino del QR), contador y botones confirmar/cancelar para quien reservó |
| `POST /reserva/<folio>/confirmar` · `/cancelar` | Finalizan la reserva |
| `GET /mis-reservas` | Reservas de la sesión |
| `GET /qr/<folio>.png` | Imagen del QR |
| `GET /api/reservas/<folio>` | Estado y segundos restantes según el servidor |

El CRUD, login, carrito, pagos y API REST del primer parcial siguen igual. En el panel de administración se agregó el campo
**Existencias** (los productos que no lo tenían reciben 3 al iniciar la app).

## Ejecutar en local
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
set MONGO_URI=mongodb+srv://...      # (Linux/Mac: export MONGO_URI=...)
python app.py                        # http://127.0.0.1:5000
```

## Variables de entorno
| Variable | Uso |
|---|---|
| `MONGO_URI` | Cadena de MongoDB Atlas (**obligatoria en Render**) |
| `SECRET_KEY` | Clave larga y privada para las sesiones (**obligatoria en Render**) |
| `APP_BASE_URL` | Opcional: URL pública que va dentro del QR |
| `RESERVA_MINUTOS` | Opcional: 3, 4 o 5 (por defecto 5) |
| `ZONA_HORARIA` | Opcional: zona para mostrar horas (por defecto `America/Mexico_City`) |
| `ADMIN_EMAIL` | Opcional: correo que será administrador |

## Despliegue en Render
Web Service · Python 3 · Build: `pip install -r requirements.txt` · Start: `gunicorn app:app`.
Agrega las variables en *Environment* y autoriza la IP de Render en Atlas (*Network Access*).

## Pruebas obligatorias
Usar una ventana normal (usuario A) y una de incógnito (usuario B): reservar, intento de B, cancelar, vencer, confirmar,
recargar, escanear el QR, cambiar el estado y escanear de nuevo, ID inexistente (`/reserva/RS-00000000`) y revisión en otro equipo.

## Guía de entrega
Pasos de Git, Render, pruebas, informe y demostración: ver [GUIA_ENTREGA.md](GUIA_ENTREGA.md).

## Capturas
_(agregar capturas principales: tienda, reserva con contador, QR, Atlas, Render)_
