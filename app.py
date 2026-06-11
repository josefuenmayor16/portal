import os
import re
import pymysql
import requests
import urllib3
from flask import Flask, request, redirect, send_from_directory, jsonify

# Deshabilitar advertencias de certificados auto-firmados del OC300
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN OMADA OC300 LOCAL
# ==========================================
OMADA_CONTROLLER_URL = os.environ.get("OMADA_CONTROLLER_URL", "https://172.172.1.30:8043")
OMADA_USER           = os.environ.get("OMADA_USER",           "lcastillo@cobeca.com")
OMADA_PASSWORD       = os.environ.get("OMADA_PASSWORD",       "Fu5@2026*.")
OMADA_SITE_NAME      = os.environ.get("OMADA_SITE_NAME",      "SAAS TROPICAL")

# ==========================================
# CACHÉ GLOBAL (se restablece al expirar)
# ==========================================
_cache = {
    "token":    None,
    "site_id":  None,
    "omadac_id": None,
}

# ==========================================
# BASE DE DATOS
# ==========================================

def get_db_connection():
    try:
        password = os.environ.get('DB_PASSWORD', '')
        if password:
            password = password.strip()
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST', 'mysql.railway.internal'),
            user=os.environ.get('DB_USER', 'root'),
            password=password,
            database=os.environ.get('DB_NAME', 'railway'),
            port=3306,
            autocommit=True,
        )
        return conn
    except Exception as e:
        print(f"[DB] Error de conexión: {e}")
        return None

# ==========================================
# VALIDACIONES DE DATOS
# ==========================================

def validar_nombre(valor, campo="campo"):
    """Solo letras, tildes, espacios. 2-30 caracteres."""
    if not valor or not valor.strip():
        return False, f"{campo} es obligatorio."
    valor = valor.strip()
    if len(valor) < 2 or len(valor) > 30:
        return False, f"{campo} debe tener entre 2 y 30 caracteres."
    if not re.match(r"^[A-Za-záéíóúÁÉÍÓÚàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛäëïöüÄËÏÖÜñÑ\s'-]+$", valor):
        return False, f"{campo} solo puede contener letras."
    return True, valor

def validar_telefono(valor):
    """Dígitos, guiones, paréntesis, +. 7-20 caracteres."""
    if not valor or not valor.strip():
        return False, "Teléfono es obligatorio."
    valor = valor.strip()
    if not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", valor):
        return False, "Teléfono inválido (use solo dígitos, +, - o paréntesis, 7-20 caracteres)."
    return True, valor

def validar_email(valor):
    """Validación estándar de email."""
    if not valor or not valor.strip():
        return False, "Email es obligatorio."
    valor = valor.strip().lower()
    if len(valor) > 50:
        return False, "Email no puede superar 50 caracteres."
    if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", valor):
        return False, "Formato de email inválido."
    return True, valor

def validar_direccion(valor):
    """Texto libre, 5-50 caracteres."""
    if not valor or not valor.strip():
        return False, "Dirección es obligatoria."
    valor = valor.strip()
    if len(valor) < 5 or len(valor) > 50:
        return False, "Dirección debe tener entre 5 y 50 caracteres."
    return True, valor

def validar_mac(valor):
    """Acepta formatos: AA:BB:CC:DD:EE:FF o AA-BB-CC-DD-EE-FF."""
    if not valor:
        return False, "MAC no proporcionada."
    valor = valor.strip()
    if re.match(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$", valor):
        return True, valor
    return False, f"Formato de MAC inválido: {valor}"

# ==========================================
# INTEGRACIÓN OMADA OC300 (API v2 con omadacId)
# ==========================================

def _reset_cache():
    _cache["token"]     = None
    _cache["site_id"]   = None
    _cache["omadac_id"] = None

def _get_session():
    sess = requests.Session()
    sess.verify = False
    sess.headers.update({
        "Content-Type": "application/json",
        "Accept":       "application/json",
    })
    return sess

def _login(session, base_url):
    """Inicia sesión y devuelve el token. Actualiza el caché."""
    url = f"{base_url}/api/v2/login"
    payload = {"username": OMADA_USER, "password": OMADA_PASSWORD}
    print(f"[Omada] LOGIN → {url}")
    resp = session.post(url, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"[Omada] Login fallido (HTTP {resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    token = (data.get("result") or {}).get("token")
    if not token:
        print(f"[Omada] Token no encontrado en respuesta: {data}")
        return None
    _cache["token"] = token
    session.headers.update({"Csrf-Token": token})
    print(f"[Omada] Token obtenido: {token[:8]}...")
    return token

def _get_omadac_id(session, base_url):
    """Obtiene el omadacId del controlador (necesario en API v2 del OC300)."""
    if _cache["omadac_id"]:
        return _cache["omadac_id"]
    url = f"{base_url}/api/info"
    resp = session.get(url, timeout=10)
    if resp.status_code != 200:
        print(f"[Omada] No se pudo obtener omadacId (HTTP {resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    omadac_id = (data.get("result") or {}).get("omadacId") or data.get("omadacId")
    if not omadac_id:
        print(f"[Omada] omadacId no encontrado en: {data}")
        return None
    _cache["omadac_id"] = omadac_id
    print(f"[Omada] omadacId: {omadac_id}")
    return omadac_id

def _get_site_id(session, base_url, omadac_id):
    """Busca el site_id por nombre del sitio."""
    if _cache["site_id"]:
        return _cache["site_id"]

    # Intentamos primero con la ruta que incluye omadacId (OC300 firmware reciente)
    urls_a_probar = [
        f"{base_url}/{omadac_id}/api/v2/sites",
        f"{base_url}/api/v2/sites",
    ]
    for url in urls_a_probar:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            continue
        data = resp.json()
        result = data.get("result", {})
        sites = result.get("data", result) if isinstance(result, dict) else result
        if not isinstance(sites, list):
            continue
        for site in sites:
            if site.get("name") == OMADA_SITE_NAME:
                site_id = site.get("id")
                _cache["site_id"] = site_id
                print(f"[Omada] Site ID encontrado: {site_id} (nombre='{OMADA_SITE_NAME}')")
                return site_id

    print(f"[Omada] Sitio '{OMADA_SITE_NAME}' no encontrado.")
    return None

def _autorizar_mac(session, base_url, omadac_id, site_id, formatted_mac, duracion_min=1440):
    """Envía el comando de autorización al OC300."""
    # Ruta con omadacId (OC300 firmware actualizado)
    urls_a_probar = [
        f"{base_url}/{omadac_id}/api/v2/sites/{site_id}/cmd/authorizations",
        f"{base_url}/api/v2/sites/{site_id}/cmd/authorizations",
    ]
    payload = {
        "mac":      formatted_mac,
        "action":   1,              # 1 = Autorizar
        "duration": duracion_min,   # en minutos
    }
    for url in urls_a_probar:
        print(f"[Omada] Autorizando MAC {formatted_mac} → {url}")
        resp = session.post(url, json=payload, timeout=10)
        print(f"[Omada] Respuesta (HTTP {resp.status_code}): {resp.text}")
        if resp.status_code == 200:
            result = resp.json()
            if result.get("errorCode") == 0:
                return True
            # Sesión expirada
            if result.get("errorCode") in [-1000, -1005, -1200]:
                print("[Omada] Sesión expirada durante autorización.")
                return None  # señal para reintentar
    return False

def autorizar_en_omada_local(client_mac, reintentar=True):
    """
    Flujo completo de autorización en el OC300 local.
    Reintenta una vez si el token ha expirado.
    """
    global _cache

    mac_ok, mac_info = validar_mac(client_mac)
    if not mac_ok:
        print(f"[Omada] {mac_info}")
        return False

    base_url      = OMADA_CONTROLLER_URL.rstrip('/')
    formatted_mac = client_mac.replace(":", "-").replace(" ", "").upper()
    session       = _get_session()

    # 1. Login (usa caché si existe)
    token = _cache["token"]
    if token:
        session.headers.update({"Csrf-Token": token})
        print(f"[Omada] Usando token cacheado: {token[:8]}...")
    else:
        token = _login(session, base_url)
        if not token:
            return False                                            

    # 2. omadacId
    omadac_id = _get_omadac_id(session, base_url)
    if not omadac_id:
        print("[Omada] omadacId no disponible; intentando sin él.")
        omadac_id = ""  # fallback sin omadacId

    # 3. Site ID
    site_id = _get_site_id(session, base_url, omadac_id)
    if not site_id:
        _reset_cache()
        return False

    # 4. Autorización
    resultado = _autorizar_mac(session, base_url, omadac_id, site_id, formatted_mac)

    if resultado is None and reintentar:
        # Token expiró → limpiar caché y reintentar una vez
        print("[Omada] Reintentando con nuevo token...")
        _reset_cache()
        return autorizar_en_omada_local(client_mac, reintentar=False)

    if resultado is False:
        print(f"[Omada] Fallo al autorizar {formatted_mac}.")
    _cache["token"] = _cache.get("token")  # mantener caché si fue exitoso
    return resultado is True

# ==========================================
# RUTAS FLASK
# ==========================================

@app.route('/')
def index():
    return send_from_directory('.', 'registro.html')

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory('img', filename)

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    # --- Lectura de parámetros ---
    nombre   = request.form.get('nombre',   '').strip()
    apellido = request.form.get('apellido', '').strip()
    telefono = request.form.get('telefono', '').strip()
    email    = request.form.get('email',    '').strip()
    direccion= request.form.get('direccion','').strip()
    clientMac= request.form.get('clientMac','').strip()
    apMac    = request.form.get('apMac',   '').strip()
    target   = request.form.get('target',  '').strip()

    print(f"[Registro] Parámetros recibidos: {dict(request.form)}")

    # --- Validaciones ---
    errores = []

    ok, val = validar_nombre(nombre, "Nombre")
    if ok: nombre = val
    else:  errores.append(val)

    ok, val = validar_nombre(apellido, "Apellido")
    if ok: apellido = val
    else:  errores.append(val)

    ok, val = validar_telefono(telefono)
    if ok: telefono = val
    else:  errores.append(val)

    ok, val = validar_email(email)
    if ok: email = val
    else:  errores.append(val)

    ok, val = validar_direccion(direccion)
    if ok: direccion = val
    else:  errores.append(val)

    if errores:
        print(f"[Registro] Validación fallida: {errores}")
        return jsonify({"error": " | ".join(errores)}), 400

    # --- Persistencia en BD ---
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Error de conexión con la base de datos."}), 500

    try:
        with conn.cursor() as cursor:
            sql_cliente = """
                INSERT INTO clientes (nombre, apellido, telefono, email, direccion)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql_cliente, (nombre, apellido, telefono, email, direccion))
            id_usuario_nuevo = cursor.lastrowid

            sql_fecha = "INSERT INTO fecha_registro (id_usuario_fr, fecha_registro) VALUES (%s, NOW())"
            cursor.execute(sql_fecha, (id_usuario_nuevo,))

        conn.close()
        print(f"[Registro] Usuario #{id_usuario_nuevo} guardado: {nombre} {apellido} <{email}>")

    except Exception as e:
        print(f"[Registro] Error al guardar en BD: {e}")
        conn.close()
        return jsonify({"error": "Error interno al guardar el registro."}), 500

    # --- Autorización en Omada ---
    if clientMac:
        mac_limpia = clientMac.replace("-", ":").strip().lower()
        print(f"[Registro] Autorizando MAC: {mac_limpia}")
        autorizado = autorizar_en_omada_local(mac_limpia)
        if autorizado:
            print(f"[Registro] ✔ Dispositivo {mac_limpia} con acceso a internet.")
        else:
            print(f"[Registro] ✘ No se pudo autorizar {mac_limpia} en Omada (registrado igual).")
    else:
        print("[Registro] Sin clientMac → autorización omitida.")

    # --- Redirección final ---
    redirect_to = target if target else "https://www.google.com"
    print(f"[Registro] Redirigiendo a: {redirect_to}")
    return redirect(redirect_to)


if __name__ == '__main__':
    print("=== Portal Cautivo - Servidor Flask ===")
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host='0.0.0.0', port=5000, debug=debug)