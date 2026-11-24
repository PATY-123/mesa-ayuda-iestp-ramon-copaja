import os  # Permite leer variables de entorno (puerto, BD, CORS y JWT)
from datetime import datetime, timedelta, timezone  # Calcula fechas de expiración de tokens en UTC
from functools import wraps  # Conserva metadatos en decoradores de rutas

from flask import Flask, jsonify, request, send_from_directory  # Framework Flask, JSON, peticiones y archivos estáticos
from flask_cors import CORS  # Configura políticas CORS para orígenes autorizados
import jwt  # Codifica y decodifica tokens JWT
import mysql.connector  # Conector oficial de Python hacia MySQL
from werkzeug.security import check_password_hash, generate_password_hash  # Genera y verifica hashes de contraseñas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Ruta absoluta de la carpeta del backend
FRONTEND_DIR = os.path.join(BASE_DIR, "helpdesk-frontend")  # Ruta de la carpeta del frontend

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")  # Sirve también archivos del frontend si se abren desde Flask

# Lee la clave secreta JWT desde el entorno; usa un valor de respaldo solo en desarrollo local
JWT_SECRET = os.getenv("JWT_SECRET", "clave_secreta_iestp_ramon_copaja_2026")

# Lee orígenes adicionales desde variable de entorno (separados por coma) junto a los locales
origenes_extra = [
    origen.strip()
    for origen in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origen.strip()
]
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    *origenes_extra,
]

# Configura CORS para las rutas bajo /api/*
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},  # Restringe acceso a orígenes permitidos
    allow_headers=["Content-Type", "Authorization"],  # Permite enviar JSON y token Bearer
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],  # Métodos HTTP habilitados
)

# Configuración de MySQL tomada desde variables de entorno (nunca hardcodear credenciales reales ni localhost en producción)
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),  # Host del servidor MySQL
    "port": int(os.getenv("DB_PORT", "3306")),  # Puerto del servidor MySQL
    "user": os.getenv("DB_USER", "root"),  # Usuario asignado a la base de datos
    "password": os.getenv("DB_PASSWORD", ""),  # Contraseña configurada en variables de entorno
    "database": os.getenv("DB_NAME", "mesa_ayuda_iestp"),  # Nombre de la base de datos
}


def conectar_bd():
    """Abre y devuelve una conexión nueva hacia MySQL."""
    return mysql.connector.connect(**DB_CONFIG)  # Conecta usando los parámetros de DB_CONFIG


def inicializar_usuarios_demo():
    """Inserta los 3 usuarios de prueba del curso si la tabla usuarios está vacía."""
    conexion = None  # Inicializa referencia de conexión
    cursor = None  # Inicializa referencia de cursor
    try:
        conexion = conectar_bd()  # Abre conexión a MySQL
        cursor = conexion.cursor(dictionary=True)  # Crea cursor que devuelve diccionarios
        cursor.execute("SELECT COUNT(*) AS total FROM usuarios")  # Cuenta registros en usuarios
        fila = cursor.fetchone()  # Obtiene resultado del conteo
        if fila and fila["total"] > 0:  # Si ya existen usuarios, evita duplicarlos
            return

        usuarios_demo = [
            ("Admin TI", "admin@iestp.local", "admin", "admin123"),  # Usuario demo administrador
            ("Tecnico 1", "tecnico1@iestp.local", "tecnico", "tec123"),  # Usuario demo técnico
            ("Estudiante 1", "estudiante1@iestp.local", "solicitante", "est123"),  # Usuario demo solicitante
        ]
        for nombres, correo, rol, clave in usuarios_demo:  # Inserta cada usuario con contraseña hasheada
            cursor.execute(
                """
                INSERT INTO usuarios (nombres, correo, rol, password_hash, activo)
                VALUES (%s, %s, %s, %s, 1)
                """,
                (nombres, correo, rol, generate_password_hash(clave)),
            )
        conexion.commit()  # Confirma cambios en MySQL
    except Exception as exc:
        print(f"Aviso al inicializar usuarios demo: {exc}")  # Informa el aviso sin detener el servidor
    finally:
        if cursor:  # Cierra cursor si existe
            cursor.close()
        if conexion:  # Cierra conexión si está abierta
            conexion.close()


def auth_required(f):
    """Exige cabecera Authorization: Bearer <token> válida; responde 401 si falla."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        encabezado = request.headers.get("Authorization", "")  # Lee cabecera Authorization
        partes = encabezado.split(" ")  # Divide en esquema y token
        if len(partes) != 2 or partes[0] != "Bearer" or not partes[1].strip():  # Verifica formato Bearer <token>
            return jsonify({"error": "Token requerido"}), 401
        try:
            payload = jwt.decode(partes[1].strip(), JWT_SECRET, algorithms=["HS256"])  # Valida firma y vigencia
            request.user = payload  # Guarda datos del usuario en la petición
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expirado"}), 401  # Token vencido
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401  # Token no válido
        return f(*args, **kwargs)  # Continúa hacia el endpoint protegido

    return wrapper


def require_role(*roles_permitidos):
    """Verifica que el rol del usuario en el token esté autorizado; responde 403 si no."""

    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            usuario = getattr(request, "user", None) or {}  # Obtiene payload autenticado
            if usuario.get("rol") not in roles_permitidos:  # Comprueba si tiene rol permitido
                return jsonify({"error": "No autorizado (rol insuficiente)"}), 403
            return f(*args, **kwargs)  # Permite ejecutar la acción

        return wrapper

    return decorador


@app.get("/")
def raiz_frontend():
    """Sirve index.html si se accede al dominio principal."""
    return send_from_directory(FRONTEND_DIR, "index.html")  # Devuelve la interfaz principal


@app.get("/api/health")
def salud():
    """Endpoint de comprobación del estado del servicio."""
    return jsonify({"estado": "ok", "servicio": "helpdesk-flask-seguro"}), 200  # Respuesta de estado


@app.post("/api/auth/login")
def login():
    """Autentica correo y contraseña contra MySQL y retorna un JWT."""
    datos = request.get_json(silent=True) or {}  # Lee JSON enviado
    correo = (datos.get("correo") or "").strip().lower()  # Normaliza correo
    password = datos.get("password") or ""  # Obtiene contraseña

    if not correo or "@" not in correo or len(password) < 3:  # Valida datos mínimos
        return jsonify({"error": "Correo o contraseña con formato inválido"}), 400

    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()  # Conecta a MySQL
        cursor = conexion.cursor(dictionary=True)  # Cursor diccionario
        cursor.execute(
            "SELECT id, nombres, correo, rol, password_hash, activo FROM usuarios WHERE correo = %s LIMIT 1",
            (correo,),  # Consulta parametrizada
        )
        usuario = cursor.fetchone()  # Obtiene usuario encontrado

        if not usuario or usuario["activo"] != 1:  # Verifica que exista y esté activo
            return jsonify({"error": "Credenciales inválidas"}), 401

        if not check_password_hash(usuario["password_hash"], password):  # Valida contraseña contra hash
            return jsonify({"error": "Credenciales inválidas"}), 401

        payload = {
            "id": usuario["id"],  # ID del usuario
            "correo": usuario["correo"],  # Correo del usuario
            "rol": usuario["rol"],  # Rol del usuario
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),  # Caduca en 1 hora
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")  # Firma el JWT
        return jsonify({"token": token, "rol": usuario["rol"], "correo": usuario["correo"]}), 200
    except Exception as exc:
        return jsonify({"error": f"Error en login: {str(exc)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()


@app.get("/api/tickets")
@auth_required
def listar_tickets():
    """Lista tickets (requiere token válido -> 401 si no hay)."""
    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()  # Conecta a MySQL
        cursor = conexion.cursor(dictionary=True)  # Cursor diccionario

        if request.user.get("rol") == "solicitante":  # Filtra solo tickets propios si es solicitante
            cursor.execute(
                """
                SELECT id, titulo, descripcion, categoria, prioridad, estado, creado_en, solicitante_id
                FROM tickets
                WHERE solicitante_id = %s
                ORDER BY id DESC
                """,
                (request.user.get("id"),),
            )
        else:  # Técnicos y administradores ven todos los tickets
            cursor.execute(
                """
                SELECT id, titulo, descripcion, categoria, prioridad, estado, creado_en, solicitante_id
                FROM tickets
                ORDER BY id DESC
                """
            )

        filas = cursor.fetchall()  # Recupera tickets
        for fila in filas:  # Convierte fechas a string para JSON
            if fila.get("creado_en") is not None:
                fila["creado_en"] = str(fila["creado_en"])

        return jsonify(filas), 200
    except Exception as exc:
        return jsonify({"error": f"Error al consultar tickets: {str(exc)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()


@app.post("/api/tickets")
@auth_required
def crear_ticket():
    """Crea un ticket validando título y prioridad (400 si son inválidos)."""
    datos = request.get_json(silent=True) or {}  # Lee JSON de entrada
    titulo = (datos.get("titulo") or "").strip()  # Limpia título
    descripcion = (datos.get("descripcion") or "").strip()  # Limpia descripción
    categoria = (datos.get("categoria") or "General").strip() or "General"  # Categoría por defecto
    prioridad = (datos.get("prioridad") or "Media").strip() or "Media"  # Prioridad por defecto

    prioridades_validas = {"Baja", "Media", "Alta", "Critica"}  # Valores permitidos de prioridad
    if len(titulo) < 5 or len(titulo) > 120:  # Valida longitud del título
        return jsonify({"error": "El título es obligatorio y debe tener entre 5 y 120 caracteres"}), 400
    if prioridad not in prioridades_validas:  # Valida prioridad
        return jsonify({"error": "Prioridad inválida. Use Baja, Media, Alta o Critica"}), 400

    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()  # Conecta a MySQL
        cursor = conexion.cursor(dictionary=True)  # Cursor diccionario
        cursor.execute(
            """
            INSERT INTO tickets (titulo, descripcion, categoria, prioridad, estado, solicitante_id)
            VALUES (%s, %s, %s, %s, 'Abierto', %s)
            """,
            (titulo, descripcion, categoria, prioridad, request.user.get("id")),  # Asocia ticket al usuario autenticado
        )
        conexion.commit()  # Confirma inserción
        nuevo_id = cursor.lastrowid  # Obtiene ID creado

        cursor.execute(
            """
            SELECT id, titulo, descripcion, categoria, prioridad, estado, creado_en, solicitante_id
            FROM tickets WHERE id = %s
            """,
            (nuevo_id,),
        )
        creado = cursor.fetchone()  # Obtiene registro insertado
        if creado and creado.get("creado_en") is not None:
            creado["creado_en"] = str(creado["creado_en"])

        return jsonify(creado), 201
    except Exception as exc:
        if conexion:
            conexion.rollback()  # Revierte ante error
        return jsonify({"error": f"Error al crear ticket: {str(exc)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()


@app.patch("/api/tickets/<int:ticket_id>")
@auth_required
@require_role("tecnico", "admin")
def actualizar_estado_ticket(ticket_id):
    """Cambia el estado de un ticket solo para roles tecnico/admin; valida estado (400)."""
    datos = request.get_json(silent=True) or {}  # Lee JSON de entrada
    estado = (datos.get("estado") or "").strip()  # Obtiene nuevo estado
    estados_validos = {"Abierto", "EnProceso", "Cerrado"}  # Estados permitidos

    if estado not in estados_validos:  # Valida estado
        return jsonify({"error": "Estado inválido. Use Abierto, EnProceso o Cerrado"}), 400

    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()  # Conecta a MySQL
        cursor = conexion.cursor(dictionary=True)  # Cursor diccionario
        cursor.execute(
            "UPDATE tickets SET estado = %s WHERE id = %s",  # Actualiza estado en MySQL
            (estado, ticket_id),
        )
        conexion.commit()  # Guarda cambio

        if cursor.rowcount == 0:  # Verifica si el ticket existía
            return jsonify({"error": "Ticket no encontrado"}), 404

        cursor.execute(
            """
            SELECT id, titulo, descripcion, categoria, prioridad, estado, creado_en, solicitante_id
            FROM tickets WHERE id = %s
            """,
            (ticket_id,),
        )
        actualizado = cursor.fetchone()  # Consulta registro actualizado
        if actualizado and actualizado.get("creado_en") is not None:
            actualizado["creado_en"] = str(actualizado["creado_en"])

        return jsonify(actualizado), 200
    except Exception as exc:
        if conexion:
            conexion.rollback()  # Revierte ante error
        return jsonify({"error": f"Error al actualizar ticket: {str(exc)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()


if __name__ == "__main__":
    inicializar_usuarios_demo()  # Inserta usuarios demo si la tabla está vacía
    puerto = int(os.getenv("PORT", "5001"))  # Toma puerto de la plataforma o 5001 en local
    modo_debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"  # Debug desactivado por defecto
    app.run(host="0.0.0.0", port=puerto, debug=modo_debug)  # Escucha en todas las interfaces