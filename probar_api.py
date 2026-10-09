import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:5000"

def pedir(metodo, ruta, datos=None):
    cuerpo = None if datos is None else json.dumps(datos).encode()
    peticion = Request(
        BASE + ruta, data=cuerpo, method=metodo,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urlopen(peticion, timeout=30) as respuesta:
            texto = respuesta.read().decode()
            print(metodo, ruta, respuesta.status, texto)
            return json.loads(texto) if texto else None
    except HTTPError as error:
        print("Error:", error.code, error.read().decode())
        raise

# 1. Crear un registro de prueba vía POST
producto = pedir("POST", "/api/productos", {
    "nombre": "Prueba API", 
    "categoria": "GPU",
    "estado": "Disponible"
})

ruta = "/api/productos/" + producto["id"]

# 2. Consultar el registro recien creado vía GET por ID
pedir("GET", ruta)

# 3. Modificar el registro vía PUT
pedir("PUT", ruta, {
    "nombre": "Prueba API", 
    "categoria": "GPU",
    "estado": "Agotado"
})

# 4. Consultar la lista completa vía GET
pedir("GET", "/api/productos")

# 5. Eliminar el registro de prueba vía DELETE
pedir("DELETE", ruta)