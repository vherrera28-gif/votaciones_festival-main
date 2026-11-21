# Votaciones · Festival de la Leyenda Vallenata

Aplicación web con **Python, Django (patrón MVT) y MySQL**. Paleta: rojo, vinotinto, negro y blanco.

## Estructura (MVT)

| Capa | Archivos |
|---|---|
| Modelo | `festival/models.py` (Edición → Categoría → Votación → Opción; Votante, Voto, CalificacionJurado) |
| Vista | `festival/views.py`, `festival/services.py` (reglas de negocio) |
| Plantilla | `festival/templates/festival/` y `festival/static/festival/css/estilo.css` |
| Rutas | `config/urls.py`, `festival/urls.py` |

## Pasos

1. **Entorno**
   ```bash
   python -m venv venv
   # Windows: venv\Scripts\activate    Linux/Mac: source venv/bin/activate
   pip install -r requirements.txt
   pip install python-dotenv
   ```
   Si `mysqlclient` falla en Windows: `pip install pymysql` y en `config/__init__.py` agrega
   `import pymysql; pymysql.install_as_MySQLdb()`.

2. **Base de datos MySQL**
   ```sql
   CREATE DATABASE votaciones_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
   Crear un archivo .env en la raíz del proyecto (junto a manage.py) con el siguiente contenido:

   DJANGO_SECRET_KEY=cambiar-esta-clave-en-produccion
   DJANGO_DEBUG=1

      DB_ENGINE=mysql
      DB_NAME=votaciones_db
      DB_USER=root
      DB_PASSWORD=tu_contraseña_mysql
      DB_HOST=localhost
      DB_PORT=3306

   Define las credenciales por variables de entorno (o edita `config/settings.py`):
   `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
   Para probar sin MySQL: `DB_ENGINE=sqlite`.
   
   Por seguridad, las credenciales de conexión a MySQL no se almacenan directamente en el código fuente. El proyecto utiliza variables de entorno cargadas desde el archivo .env.

Para probar sin MySQL:

3. **Migraciones** (ya vienen incluidas en `festival/migrations/`)
   ```bash
   python manage.py migrate
   ```

4. **Django Admin y datos de prueba**
   ```bash
   python manage.py cargar_datos_prueba
   python manage.py runserver
   ```
   - Admin: `admin / admin12345` · Jurado: `jurado1 / jurado12345` (cámbialas fuera de pruebas)
   - Votante: cédula `1234567890`, celular `3001234567` (el código aparece en pantalla en modo demostración)
   - Django Admin: `http://127.0.0.1:8000/admin/` · Panel propio: `http://127.0.0.1:8000/panel/`

5. **Pruebas**
   ```bash
   python manage.py test festival // ejecutar todas las pruebas que estan dentro de test

   ```

## Regla de identificación (propuesta, por confirmar con la Fundación)

La **cédula identifica** a la persona; el **celular** solo verifica con un código de un solo uso.
Cédula única, celular único y restricciones únicas `(votante, votación, número de voto)` y `(votante, categoría, número de voto)` en la base de datos.
Con el límite por defecto (1 voto) equivale a un voto por votante y categoría (y, como cada categoría pertenece a una sola edición, por edición), aunque la categoría tenga varias votaciones.

## Parámetros sin tocar código

- Por votación (Django Admin o `/panel/votaciones/`): apertura, cierre, `peso_jurado`, `exigir_mayoria_edad`, `votos_por_votante`, `pausada`.
- Globales (`config/settings.py`): `REGLAS_CONFIRMADAS_POR_FUNDACION` (mientras sea `False`, la interfaz marca las reglas como «por confirmar»), `CODIGOS_MAX_POR_HORA`, `CODIGO_VIGENCIA_MIN`, `CUARENTENA_VOTOS_POR_IP`, `MOSTRAR_CODIGO_EN_PANTALLA`.
- Nueva edición: crearla en Django Admin y marcarla como activa; sus categorías y votaciones se cargan igual, sin cambiar código.

## Pruebas

```bash
python manage.py test festival
```

- **Concurrencia real:** la clase `ConcurrenciaMySQLTests` lanza hilos que votan al mismo tiempo y luego
  consulta la base. Solo se ejecuta con MySQL (con SQLite se omite, porque `select_for_update` no aplica).
- **Prueba de carga:** `python manage.py prueba_carga --votantes 200 --hilos 20` simula muchos votantes
  votando a la vez, repite las solicitudes para probar duplicados y verifica los registros en la base.
  Crea usuarios temporales `carga_*` y los borra al terminar (`--conservar` para dejarlos).
- **Otra edición:** `python manage.py cargar_datos_prueba --anio 2028` crea y activa otra edición sin tocar código.

## Pendientes antes de producción

- Configurar DJANGO_DEBUG=0 y una DJANGO_SECRET_KEY propia mediante variables de entorno.
- Utilizar un archivo .env exclusivo para producción.
- Habilitar HTTPS. Detrás de un proxy, REMOTE_ADDR no es la IP real del votante.

## Seguridad

Las credenciales sensibles (contraseña de MySQL y clave secreta de Django) se almacenan mediante variables de entorno en el archivo `.env`.

Agregar el archivo `.env` al `.gitignore` para evitar publicar información sensible:

```gitignore
.env