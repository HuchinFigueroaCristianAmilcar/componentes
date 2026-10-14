from flask import (
    Flask, render_template, request, redirect, url_for, abort, jsonify,
    session, flash,
)
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import secrets

app = Flask(__name__)

# Clave para firmar las sesiones (login y carrito). Definela en Render.
clave = os.environ.get("SECRET_KEY")
if not clave:
    if os.environ.get("RENDER"):
        raise RuntimeError("Configura SECRET_KEY en Render.")
    clave = "clave-solo-para-desarrollo-local"
app.config.update(
    SECRET_KEY=clave,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

# Lee la variable de entorno desde Render
mongo_uri = os.environ.get("MONGO_URI") 

if not mongo_uri:
    if os.environ.get("RENDER"):
        raise RuntimeError("Configura MONGO_URI en Render.")
    # Solo usa la base de datos local si NO estamos en Render y NO hay MONGO_URI definida
    mongo_uri = "mongodb://127.0.0.1:27017/"

cliente = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
base_datos = cliente["componentes"]
articulos = base_datos["articulos"]
usuarios = base_datos["usuarios"]
pedidos = base_datos["pedidos"]

ENVIO_COSTO = 129.0
ENVIO_GRATIS_DESDE = 2000.0

def leer_formulario(datos=None):
    if datos is None:
        datos = request.form
    campos = ("nombre", "categoria", "estado")
    if any(not isinstance(datos.get(c, ""), str) for c in campos):
        abort(400, description="Los campos deben contener texto.")
    nombre = datos.get("nombre", "").strip()
    categoria = datos.get("categoria", "").strip()
    estado = datos.get("estado", "").strip()
    if not nombre or not categoria or not estado:
        abort(400, description="Completa nombre, categoría y estado.")
    if len(nombre) > 80 or len(categoria) > 20:
        abort(400, description="Máximo: nombre 80 y categoría 20.")
    if estado not in ["Disponible", "Agotado"]:
        abort(400, description="Selecciona un estado válido.")
    resultado = {"nombre": nombre, "categoria": categoria, "estado": estado}

    # Campos opcionales de la tienda (solo se guardan si vienen en la petición)
    if "precio" in datos:
        bruto = datos.get("precio")
        if isinstance(bruto, bool) or not isinstance(bruto, (str, int, float)):
            abort(400, description="El precio debe ser un número.")
        try:
            precio = float(str(bruto).strip().replace(",", "") or 0)
        except ValueError:
            abort(400, description="El precio debe ser un número.")
        if not 0 <= precio <= 1_000_000:
            abort(400, description="El precio debe estar entre 0 y 1,000,000.")
        resultado["precio"] = round(precio, 2)
    if "descripcion" in datos:
        descripcion = datos.get("descripcion")
        if not isinstance(descripcion, str) or len(descripcion.strip()) > 400:
            abort(400, description="La descripción admite hasta 400 caracteres.")
        resultado["descripcion"] = descripcion.strip()
    if "imagen" in datos:
        imagen = datos.get("imagen")
        if not isinstance(imagen, str) or len(imagen.strip()) > 300:
            abort(400, description="La URL de imagen es demasiado larga.")
        imagen = imagen.strip()
        if imagen and not re.match(r"^https?://", imagen, re.I):
            abort(400, description="La imagen debe ser una URL http(s).")
        resultado["imagen"] = imagen
    return resultado

def buscar_articulo(id):
    if not ObjectId.is_valid(id):
        abort(404, description="La clave del producto no es válida.")
    articulo = articulos.find_one({"_id": ObjectId(id)})
    if articulo is None:
        abort(404, description="Este producto ya no existe.")
    return articulo

# ---------------------------------------------------------------------------
# Sesión, seguridad y utilidades de la tienda
# ---------------------------------------------------------------------------
def usuario_actual():
    if "usuario_id" not in session:
        return None
    return {
        "id": session["usuario_id"],
        "nombre": session.get("usuario_nombre", ""),
        "rol": session.get("usuario_rol", "cliente"),
    }

def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not usuario_actual():
            flash("Inicia sesión para continuar.", "warning")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return vista(*args, **kwargs)
    return envoltura

def admin_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = usuario_actual()
        if not usuario:
            flash("Inicia sesión como administrador.", "warning")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        if usuario["rol"] != "admin":
            abort(403, description="Solo el administrador puede gestionar productos.")
        return vista(*args, **kwargs)
    return envoltura

def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]

@app.before_request
def verificar_csrf():
    # La API REST (JSON) queda fuera; los formularios web deben traer token.
    if request.method == "POST" and not request.path.startswith("/api/"):
        enviado = request.form.get("csrf", "")
        if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
            abort(400, description="La sesión del formulario expiró. Recarga la página e inténtalo de nuevo.")

@app.context_processor
def inyectar_globales():
    carrito = session.get("carrito", {})
    return {
        "csrf_token": token_csrf,
        "usuario": usuario_actual(),
        "carrito_total": sum(carrito.values()) if isinstance(carrito, dict) else 0,
        "envio_gratis": ENVIO_GRATIS_DESDE,
    }

@app.template_filter("dinero")
def filtro_dinero(valor):
    try:
        return "${:,.2f}".format(float(valor))
    except (TypeError, ValueError):
        return "$0.00"

def precio_de(articulo):
    try:
        return float(articulo.get("precio", 0) or 0)
    except (TypeError, ValueError):
        return 0.0

def destino_seguro(destino):
    # Evita redirecciones abiertas: solo rutas internas.
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return url_for("inicio")

# ---------------------------------------------------------------------------
# Tienda: inicio, productos, detalle, información
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    destacados = list(articulos.find({"estado": "Disponible"}).sort("nombre", 1).limit(8))
    categorias = sorted(c for c in articulos.distinct("categoria") if c)
    total = articulos.count_documents({})
    return render_template(
        "index.html", destacados=destacados, categorias=categorias, total=total
    )

@app.route("/productos")
def productos():
    q = request.args.get("q", "").strip()[:60]
    categoria = request.args.get("categoria", "").strip()[:20]
    orden = request.args.get("orden", "nombre")
    filtro = {}
    if q:
        filtro["nombre"] = {"$regex": re.escape(q), "$options": "i"}
    if categoria:
        filtro["categoria"] = categoria
    criterios = {
        "nombre": ("nombre", 1),
        "precio_asc": ("precio", 1),
        "precio_desc": ("precio", -1),
    }
    campo, sentido = criterios.get(orden, criterios["nombre"])
    lista = list(articulos.find(filtro).sort(campo, sentido))
    categorias = sorted(c for c in articulos.distinct("categoria") if c)
    return render_template(
        "productos.html", articulos=lista, categorias=categorias,
        q=q, categoria=categoria, orden=orden,
    )

@app.route("/producto/<id>")
def producto(id):
    articulo = buscar_articulo(id)
    relacionados = list(
        articulos.find({"categoria": articulo["categoria"], "_id": {"$ne": articulo["_id"]}}).limit(4)
    )
    return render_template("producto.html", articulo=articulo, relacionados=relacionados)

@app.route("/informacion")
def informacion():
    return render_template("informacion.html", envio_gratis=ENVIO_GRATIS_DESDE, envio_costo=ENVIO_COSTO)

# ---------------------------------------------------------------------------
# Cuentas: registro, inicio y cierre de sesión
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def iniciar_sesion(u):
    siguiente_carrito = session.get("carrito", {})
    session.clear()
    session["carrito"] = siguiente_carrito
    session["usuario_id"] = str(u["_id"])
    session["usuario_nombre"] = u["nombre"]
    session["usuario_rol"] = u.get("rol", "cliente")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        clave1 = request.form.get("password", "")
        clave2 = request.form.get("password2", "")
        error = None
        if not nombre or len(nombre) > 60:
            error = "Escribe tu nombre (máximo 60 caracteres)."
        elif not EMAIL_RE.match(email) or len(email) > 120:
            error = "Escribe un correo válido."
        elif len(clave1) < 8:
            error = "La contraseña debe tener al menos 8 caracteres."
        elif clave1 != clave2:
            error = "Las contraseñas no coinciden."
        elif usuarios.find_one({"email": email}):
            error = "Ya existe una cuenta con ese correo."
        if error:
            flash(error, "danger")
            return render_template("registro.html", nombre=nombre, email=email), 400
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        # El primer usuario registrado (o ADMIN_EMAIL) administra el catálogo.
        es_admin = usuarios.count_documents({}) == 0 or (admin_email and email == admin_email)
        nuevo = {
            "nombre": nombre, "email": email,
            "password": generate_password_hash(clave1),
            "rol": "admin" if es_admin else "cliente",
            "creado": datetime.now(),
        }
        nuevo["_id"] = usuarios.insert_one(nuevo).inserted_id
        iniciar_sesion(nuevo)
        flash("¡Cuenta creada! Bienvenido, %s." % nombre, "success")
        return redirect(url_for("inicio"))
    return render_template("registro.html", nombre="", email="")

@app.route("/login", methods=["GET", "POST"])
def login():
    siguiente = request.values.get("next", "")
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave1 = request.form.get("password", "")
        u = usuarios.find_one({"email": email})
        if not u or not check_password_hash(u["password"], clave1):
            flash("Correo o contraseña incorrectos.", "danger")
            return render_template("login.html", email=email, siguiente=siguiente), 401
        iniciar_sesion(u)
        flash("Sesión iniciada. ¡Hola, %s!" % u["nombre"], "success")
        return redirect(destino_seguro(siguiente))
    return render_template("login.html", email="", siguiente=siguiente)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Cerraste sesión.", "info")
    return redirect(url_for("inicio"))

# ---------------------------------------------------------------------------
# Carrito (guardado en la sesión del navegador)
# ---------------------------------------------------------------------------
def detalle_carrito():
    """Devuelve (lineas, subtotal, envio, total) con datos frescos de la BD."""
    bruto = session.get("carrito", {})
    lineas, subtotal = [], 0.0
    for id, cantidad in list(bruto.items()):
        if not ObjectId.is_valid(id):
            continue
        art = articulos.find_one({"_id": ObjectId(id)})
        if art is None:
            continue
        precio = precio_de(art)
        importe = round(precio * cantidad, 2)
        subtotal += importe
        lineas.append({
            "articulo": art, "id": id, "cantidad": cantidad,
            "precio": precio, "importe": importe,
            "disponible": art.get("estado") == "Disponible" and precio > 0,
        })
    subtotal = round(subtotal, 2)
    envio = 0.0 if (not lineas or subtotal >= ENVIO_GRATIS_DESDE) else ENVIO_COSTO
    return lineas, subtotal, envio, round(subtotal + envio, 2)

@app.route("/carrito")
def carrito():
    lineas, subtotal, envio, total = detalle_carrito()
    hay_no_disponibles = any(not l["disponible"] for l in lineas)
    return render_template(
        "carrito.html", lineas=lineas, subtotal=subtotal, envio=envio, total=total,
        faltante=max(0, ENVIO_GRATIS_DESDE - subtotal), gratis_desde=ENVIO_GRATIS_DESDE,
        hay_no_disponibles=hay_no_disponibles,
    )

@app.route("/carrito/agregar/<id>", methods=["POST"])
def carrito_agregar(id):
    art = buscar_articulo(id)
    if art.get("estado") != "Disponible" or precio_de(art) <= 0:
        flash("Este producto no está disponible para compra.", "warning")
        return redirect(destino_seguro(request.form.get("volver", "")) if request.form.get("volver") else url_for("productos"))
    try:
        cantidad = max(1, min(int(request.form.get("cantidad", 1)), 10))
    except ValueError:
        cantidad = 1
    carrito_s = dict(session.get("carrito", {}))
    carrito_s[id] = min(carrito_s.get(id, 0) + cantidad, 10)
    session["carrito"] = carrito_s
    flash("«%s» se agregó al carrito." % art["nombre"], "success")
    if request.form.get("ir") == "carrito":
        return redirect(url_for("carrito"))
    return redirect(destino_seguro(request.form.get("volver", "")) if request.form.get("volver") else url_for("productos"))

@app.route("/carrito/actualizar/<id>", methods=["POST"])
def carrito_actualizar(id):
    carrito_s = dict(session.get("carrito", {}))
    if id in carrito_s:
        try:
            cantidad = int(request.form.get("cantidad", 1))
        except ValueError:
            cantidad = 1
        if cantidad <= 0:
            carrito_s.pop(id)
        else:
            carrito_s[id] = min(cantidad, 10)
        session["carrito"] = carrito_s
    return redirect(url_for("carrito"))

@app.route("/carrito/quitar/<id>", methods=["POST"])
def carrito_quitar(id):
    carrito_s = dict(session.get("carrito", {}))
    carrito_s.pop(id, None)
    session["carrito"] = carrito_s
    return redirect(url_for("carrito"))

@app.route("/carrito/vaciar", methods=["POST"])
def carrito_vaciar():
    session["carrito"] = {}
    return redirect(url_for("carrito"))

# ---------------------------------------------------------------------------
# Pagos (simulados: no se procesa ni se guarda ningún dato real de tarjeta)
# ---------------------------------------------------------------------------
def luhn_valido(numero):
    digitos = [int(d) for d in numero][::-1]
    suma = sum(digitos[0::2]) + sum(sum(divmod(d * 2, 10)) for d in digitos[1::2])
    return suma % 10 == 0

def validar_pago(form):
    datos = {
        "nombre": form.get("nombre", "").strip(),
        "telefono": re.sub(r"[\s-]", "", form.get("telefono", "")),
        "direccion": form.get("direccion", "").strip(),
        "ciudad": form.get("ciudad", "").strip(),
        "cp": form.get("cp", "").strip(),
        "metodo": form.get("metodo", ""),
    }
    if not datos["nombre"] or not datos["direccion"] or not datos["ciudad"]:
        return datos, "Completa nombre, dirección y ciudad de envío."
    if len(datos["nombre"]) > 80 or len(datos["direccion"]) > 150 or len(datos["ciudad"]) > 60:
        return datos, "Alguno de los datos de envío es demasiado largo."
    if not re.fullmatch(r"\d{5}", datos["cp"]):
        return datos, "El código postal debe tener 5 dígitos."
    if not re.fullmatch(r"\d{10}", datos["telefono"]):
        return datos, "El teléfono debe tener 10 dígitos."
    if datos["metodo"] not in ("tarjeta", "transferencia", "oxxo"):
        return datos, "Elige un método de pago."
    if datos["metodo"] == "tarjeta":
        numero = re.sub(r"\s", "", form.get("tarjeta", ""))
        if not re.fullmatch(r"\d{13,19}", numero) or not luhn_valido(numero):
            return datos, "El número de tarjeta no es válido."
        m = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", form.get("vence", "").strip())
        hoy = datetime.now()
        if not m or not 1 <= int(m.group(1)) <= 12 or (2000 + int(m.group(2)), int(m.group(1))) < (hoy.year, hoy.month):
            return datos, "La fecha de vencimiento no es válida (MM/AA)."
        if not re.fullmatch(r"\d{3,4}", form.get("cvv", "")):
            return datos, "El CVV debe tener 3 o 4 dígitos."
        if not form.get("titular", "").strip():
            return datos, "Escribe el nombre del titular."
        datos["tarjeta_ultimos4"] = numero[-4:]
    return datos, None

@app.route("/pago", methods=["GET", "POST"])
@login_requerido
def pago():
    lineas, subtotal, envio, total = detalle_carrito()
    if not lineas:
        flash("Tu carrito está vacío.", "info")
        return redirect(url_for("productos"))
    if any(not l["disponible"] for l in lineas):
        flash("Quita del carrito los productos no disponibles para continuar.", "warning")
        return redirect(url_for("carrito"))
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        datos, error = validar_pago(request.form)
        if error:
            flash(error, "danger")
            return render_template(
                "pago.html", lineas=lineas, subtotal=subtotal, envio=envio,
                total=total, form=request.form,
            ), 400
        pedido = {
            "usuario_id": session["usuario_id"],
            "fecha": datetime.now(),
            "items": [
                {"id": l["id"], "nombre": l["articulo"]["nombre"],
                 "precio": l["precio"], "cantidad": l["cantidad"]}
                for l in lineas
            ],
            "subtotal": subtotal, "envio": envio, "total": total,
            "envio_a": {k: datos[k] for k in ("nombre", "telefono", "direccion", "ciudad", "cp")},
            "metodo": datos["metodo"],
            "estado": "Pagado" if datos["metodo"] == "tarjeta" else "Pendiente de pago",
            "referencia": "PC-" + secrets.token_hex(4).upper(),
        }
        if "tarjeta_ultimos4" in datos:
            pedido["tarjeta_ultimos4"] = datos["tarjeta_ultimos4"]
        pedido_id = pedidos.insert_one(pedido).inserted_id
        session["carrito"] = {}
        return redirect(url_for("pedido", id=str(pedido_id)))
    return render_template(
        "pago.html", lineas=lineas, subtotal=subtotal, envio=envio, total=total, form=form,
    )

def buscar_pedido(id):
    if not ObjectId.is_valid(id):
        abort(404, description="El pedido no es válido.")
    p = pedidos.find_one({"_id": ObjectId(id)})
    usuario = usuario_actual()
    # Un cliente solo ve sus pedidos; el admin ve todos.
    if p is None or not usuario or (p["usuario_id"] != usuario["id"] and usuario["rol"] != "admin"):
        abort(404, description="No encontramos ese pedido.")
    return p

@app.route("/pedido/<id>")
@login_requerido
def pedido(id):
    return render_template("pedido.html", pedido=buscar_pedido(id))

@app.route("/mis-pedidos")
@login_requerido
def mis_pedidos():
    lista = list(pedidos.find({"usuario_id": session["usuario_id"]}).sort("fecha", -1))
    return render_template("pedidos.html", pedidos=lista)

# ---------------------------------------------------------------------------
# Panel de administración: CRUD de productos (mismas rutas de siempre)
# ---------------------------------------------------------------------------
@app.route("/admin")
@admin_requerido
def admin():
    lista = list(articulos.find().sort("nombre", 1))
    return render_template("admin.html", articulos=lista)

@app.route("/agregar", methods=["POST"])
@admin_requerido
def agregar():
    datos = leer_formulario()
    articulos.insert_one(datos)
    flash("Producto agregado.", "success")
    return redirect(url_for("admin"))

@app.route("/editar/<id>", methods=["GET", "POST"])
@admin_requerido
def editar(id):
    articulo = buscar_articulo(id)
    if request.method == "POST":
        datos = leer_formulario()
        articulos.update_one({"_id": articulo["_id"]}, {"$set": datos})
        flash("Cambios guardados.", "success")
        return redirect(url_for("admin"))
    return render_template("editar.html", articulo=articulo)

@app.route("/eliminar/<id>", methods=["POST"])
@admin_requerido
def eliminar(id):
    articulo = buscar_articulo(id)
    articulos.delete_one({"_id": articulo["_id"]})
    flash("Producto eliminado.", "info")
    return redirect(url_for("admin"))

EJEMPLOS = [
    ("AMD Ryzen 7 7800X3D", "CPU", 8499, "8 núcleos y 96 MB de caché 3D V-Cache. Ideal para gaming de alto rendimiento."),
    ("Intel Core i5-14600K", "CPU", 6299, "14 núcleos (6P + 8E) con desbloqueo para overclock. Gran equilibrio precio-rendimiento."),
    ("NVIDIA GeForce RTX 4070 Super", "GPU", 15999, "12 GB GDDR6X, DLSS 3 y ray tracing para 1440p fluido."),
    ("AMD Radeon RX 7800 XT", "GPU", 12499, "16 GB GDDR6 y arquitectura RDNA 3. Excelente en 1440p."),
    ("Kingston Fury Beast 32GB DDR5", "RAM", 2399, "Kit 2x16 GB a 6000 MHz con perfil XMP 3.0."),
    ("Corsair Vengeance 16GB DDR4", "RAM", 899, "Kit 2x8 GB a 3200 MHz, compatible con la mayoría de plataformas."),
    ("Samsung 980 Pro 1TB NVMe", "SSD", 2299, "PCIe 4.0 con lecturas de hasta 7,000 MB/s."),
    ("WD Blue SN580 500GB", "SSD", 899, "NVMe PCIe 4.0 económico para sistema y aplicaciones."),
    ("ASUS TUF B650-PLUS WiFi", "Motherboard", 4399, "Socket AM5, DDR5, WiFi 6 y PCIe 5.0."),
    ("Corsair RM850e 850W", "Fuente", 2699, "80 Plus Gold, modular y silenciosa. Compatible con ATX 3.0."),
    ("NZXT H5 Flow", "Gabinete", 1799, "Torre media con excelente flujo de aire y gestión de cables."),
]

@app.route("/admin/ejemplos", methods=["POST"])
@admin_requerido
def admin_ejemplos():
    nuevos = 0
    for nombre, categoria, precio, descripcion in EJEMPLOS:
        if not articulos.find_one({"nombre": nombre}):
            articulos.insert_one({
                "nombre": nombre, "categoria": categoria, "estado": "Disponible",
                "precio": float(precio), "descripcion": descripcion, "imagen": "",
            })
            nuevos += 1
    flash("Se cargaron %d productos de ejemplo." % nuevos, "success")
    return redirect(url_for("admin"))

@app.errorhandler(PyMongoError)
def error_mongo(error):
    mensaje = "No fue posible conectar con la base de datos."
    if request.path.startswith("/api/"):
        return jsonify({"error": mensaje}), 503
    return render_template("error.html", mensaje=mensaje), 503

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
def error_peticion(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return render_template(
        "error.html", mensaje=error.description
    ), error.code

@app.route("/ayuda")
def ayuda():
    fecha = datetime.now().strftime("%d/%m/%Y")
    return render_template("ayuda.html", fecha=fecha)

# API REST - Parte 1
def producto_json(producto):
    return {
        "id": str(producto["_id"]),
        "nombre": producto["nombre"],
        "categoria": producto["categoria"],
        "estado": producto["estado"],
        "precio": producto.get("precio", 0),
        "descripcion": producto.get("descripcion", ""),
        "imagen": producto.get("imagen", "")
    }

def leer_json():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        abort(400, description="Envía un objeto JSON válido.")
    return leer_formulario(datos)

@app.route("/api/productos", methods=["GET", "POST"])
def api_productos():
    if request.method == "POST":
        datos = leer_json()
        resultado = articulos.insert_one(datos)
        producto = buscar_articulo(str(resultado.inserted_id))
        return jsonify(producto_json(producto)), 201
    lista = articulos.find().sort("nombre", 1)
    return jsonify([producto_json(p) for p in lista])

@app.route("/api/productos/<id>", methods=["GET", "PUT", "DELETE"])
def api_producto(id):
    producto = buscar_articulo(id)
    if request.method == "PUT":
        datos = leer_json()
        articulos.update_one({"_id": producto["_id"]}, {"$set": datos})
        return jsonify(producto_json(buscar_articulo(id)))
    if request.method == "DELETE":
        articulos.delete_one({"_id": producto["_id"]})
        return "", 204
    return jsonify(producto_json(producto))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)