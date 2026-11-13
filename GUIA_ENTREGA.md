# Guía de entrega paso a paso

Marca cada paso al terminarlo. Sigue el orden: la entrega solo vale si todo se probó **desde la versión publicada en Render**.

## 1. Proteger el proyecto original (antes de copiar los cambios)
Haz esto **antes** de reemplazar archivos con los de esta versión.
```bash
git status
git add .
git commit -m "Respaldo del proyecto del primer parcial"
git checkout -b proyecto-final
```
- [ ] Verifica que `.env` aparece en `.gitignore` (ya está) y que `git status` no lo muestra.
- [ ] Si ya subiste `.env` por error: avisa al docente, cambia la contraseña de Atlas y quítalo del seguimiento (`git rm --cached .env`).

Si aún no tienes repositorio:
```bash
git init
git add .
git commit -m "Respaldo del proyecto del primer parcial"
git branch -M main
git remote add origin URL_DEL_REPOSITORIO
git push -u origin main
git checkout -b proyecto-final
```

## 2. Copiar los cambios y hacer los commits (mínimo 4)
Copia los archivos nuevos sobre tu proyecto y haz un commit por etapa, **solo cuando esa etapa funcione**:

```bash
# Commit 2 – reserva y validación de disponibilidad (existencias, descuento atómico)
git add app.py templates/producto.html templates/admin.html templates/editar.html
git commit -m "Integra reserva temporal y validación de disponibilidad"

# Commit 3 – vencimiento, cancelación y confirmación (comprobante con contador)
git add templates/reserva.html templates/reservas.html templates/base.html static/estilos.css
git commit -m "Agrega vencimiento, cancelación y confirmación"

# Commit 4 – QR, dependencias, documentación y pruebas finales
git add requirements.txt README.md GUIA_ENTREGA.md
git commit -m "Agrega ficha pública, código QR y pruebas finales"

git push origin proyecto-final
```
Tip: `app.py` contiene todo el backend, así que el commit 2 lo lleva completo; si prefieres commits más finos usa `git add -p app.py`. Tus propias correcciones tras las pruebas cruzadas también deben ir en commits aparte (el historial debe mostrar el proceso real).

## 3. Probar en local (opcional pero recomendado)
```bash
pip install -r requirements.txt
set MONGO_URI=tu_cadena_de_atlas      # Linux/Mac: export MONGO_URI=...
python app.py
```
El QR dirá «localhost»: es normal en local. Para probar el QR de verdad usa Render.

## 4. Publicar en Render
1. Sube la rama a GitHub (`git push origin proyecto-final`; si Render usa `main`, haz merge o cambia la rama en Render).
2. Render → **New > Web Service** → conecta el repositorio.
3. Language: **Python 3** · Build: `pip install -r requirements.txt` · Start: `gunicorn app:app`.
4. Environment: `MONGO_URI` (cadena completa de Atlas), `SECRET_KEY` (frase larga y privada). Opcional: `APP_BASE_URL`.
5. En Atlas → Network Access, permite la conexión de Render (p. ej. `0.0.0.0/0` para la práctica).
6. Espera el deploy, abre la URL `onrender.com` y entra como administrador (el primer usuario registrado) → **Administrar → Cargar productos de ejemplo**.
7. Repite las pruebas de la sección 5 en esa URL.

Errores frecuentes: *Build failed* → revisa `requirements.txt` · *Application failed* → revisa Logs y `gunicorn app:app` · *No conecta a Atlas* → `MONGO_URI`, usuario/contraseña y Network Access · *QR abre localhost* → abre la app desde la URL de Render o define `APP_BASE_URL`.

## 5. Pruebas obligatorias (ventana normal = A, incógnito = B)
Tip: para que se note el bloqueo usa un producto con **1 existencia** (las tarjetas de más de $15,000 de los ejemplos ya la traen).

| N.º | Prueba | Resultado esperado | Evidencia a capturar |
|---|---|---|---|
| 1 | A aparta un producto | Aparece el contador y Atlas guarda la reserva (`reservas`) | Captura del contador + documento en Atlas |
| 2 | B intenta apartar el mismo producto | Mensaje «No hay unidades disponibles…» | Captura del mensaje de B |
| 3 | A cancela | El producto vuelve a estar disponible para B | Captura antes/después de B |
| 4 | A aparta y espera 5 min | La reserva pasa a «Vencida» y las existencias regresan | Captura antes/después (Atlas: `estado`, `existencias`) |
| 5 | A confirma antes de vencer | Estado «Confirmada», el contador desaparece | Captura |
| 6 | Recargar / reabrir la app | El estado se conserva (está en Atlas) | Captura de Atlas |
| 7 | Escanear el QR con el celular | Abre el comprobante en Render | Foto o captura del celular |
| 8 | Cambiar el estado (p. ej. confirmar) y escanear el mismo QR | Muestra el estado nuevo | Captura |
| 9 | Abrir `/reserva/RS-00000000` | Mensaje claro, la app no se cae | Captura |
| 10 | Revisar el proyecto en otro equipo | No depende de archivos personales ni de localhost | Registro de la prueba |

Registro de prueba cruzada (otro equipo prueba tu Render): equipo · prueba superada · error encontrado · corrección realizada.

## 6. Informe PDF (5 a 8 páginas)
1. Portada: plantel, materia, proyecto, equipo, grupo y fecha.
2. Proyecto original: descripción breve y captura antes de la mejora.
3. Reserva temporal: elemento elegido (unidades de producto), duración (5 min), funcionamiento y capturas.
4. Código QR: página que abre (`/reserva/<folio>`), imagen QR y prueba en celular.
5. MongoDB Atlas: capturas de `articulos` (campo `existencias`) y `reservas`, **sin credenciales**.
6. Pruebas: tabla de la sección 5 con resultado y correcciones.
7. Publicación: capturas de GitHub (commits, README) y Render, con enlaces finales.
8. Conclusión: qué problema resolvieron y qué aprendieron.

## 7. Demostración final (máximo 7 min)
| Tiempo | Contenido |
|---|---|
| 1 min | Mostrar la tienda original y explicar la mejora (apartar unidades) |
| 3 min | A aparta → B no puede → A cancela → (vencimiento) → A confirma |
| 1 min | Escanear el QR y mostrar el comprobante publicado |
| 1 min | Mostrar Atlas (`reservas`, `existencias`), GitHub y Render |
| 1 min | Participación de cada integrante, dificultades y aprendizaje |

## 8. Preguntas que todos deben saber responder
- **¿Qué se reserva?** Unidades (`existencias`) de un producto, por 5 minutos.
- **¿Cómo se evita la doble reserva?** Un `update_one` atómico con `existencias >= cantidad` y `$inc`; solo una petición lo logra.
- **¿Qué pasa al vencer?** `expira_en` está en Atlas; `liberar_vencidas()` pasa la reserva a `vencida` y devuelve las unidades una sola vez.
- **¿Qué guarda MongoDB?** `articulos.existencias` y la colección `reservas` (folio, estado, creada_en, expira_en…).
- **¿Qué dirección contiene el QR?** `https://<app>.onrender.com/reserva/<folio>`.

## 9. Lista final antes de entregar
- [ ] Conserva las funciones del primer parcial (CRUD, login, carrito, pagos)
- [ ] Reservar, bloquear a B, cancelar, vencer y confirmar funcionan en Render
- [ ] El vencimiento está en Atlas, no solo en pantalla
- [ ] El QR abre la URL de Render desde un celular y muestra información actualizada
- [ ] Folio inexistente → mensaje claro
- [ ] GitHub sin `.env` ni credenciales, con README y mínimo 4 commits
- [ ] README completo (integrantes, grupo, enlace de Render, capturas)
- [ ] Informe PDF con enlaces y evidencias legibles
- [ ] Todos los integrantes pueden hacer la demostración
- [ ] En Classroom: nombres completos de todos y enlaces con permiso de acceso
