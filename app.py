from flask import Flask, render_template, request, redirect, url_for, abort
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime
import os

app = Flask(__name__)

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
    return {"nombre": nombre, "categoria": categoria, "estado": estado}

def buscar_articulo(id):
    if not ObjectId.is_valid(id):
        abort(404, description="La clave del producto no es válida.")
    articulo = articulos.find_one({"_id": ObjectId(id)})
    if articulo is None:
        abort(404, description="Este producto ya no existe.")
    return articulo

@app.route("/")
def inicio():
    lista = list(articulos.find().sort("nombre", 1))
    return render_template("index.html", articulos=lista)

@app.route("/agregar", methods=["POST"])
def agregar():
    datos = leer_formulario()
    articulos.insert_one(datos)
    return redirect(url_for("inicio"))

@app.route("/editar/<id>", methods=["GET", "POST"])
def editar(id):
    articulo = buscar_articulo(id)
    if request.method == "POST":
        datos = leer_formulario()
        articulos.update_one({"_id": articulo["_id"]}, {"$set": datos})
        return redirect(url_for("inicio"))
    return render_template("editar.html", articulo=articulo)

@app.route("/eliminar/<id>", methods=["POST"])
def eliminar(id):
    articulo = buscar_articulo(id)
    articulos.delete_one({"_id": articulo["_id"]})
    return redirect(url_for("inicio"))

@app.errorhandler(PyMongoError)
def error_mongo(error):
    return render_template("error.html", mensaje="No fue posible conectar con la base de datos"), 503

@app.errorhandler(400)
@app.errorhandler(404)
def error_peticion(error):
    return render_template("error.html", mensaje=error.description), error.code

@app.route("/ayuda")
def ayuda():
    fecha = datetime.now().strftime("%d/%m/%Y")
    return render_template("ayuda.html", fecha=fecha)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)