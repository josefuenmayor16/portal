import os
import pymysql
import requests
from flask import Flask, request, redirect, jsonify, send_from_directory

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE OMADA CLOUD (PRODUCCIÓN)
# ==========================================
# Railway leerá los textos planos configurados en tu panel de variables
OMADA_API_URL = os.environ.get("OMADA_API_URL", "https://use1-omada-cloud.tplinkcloud.com/api/v1")
OMADA_USER = os.environ.get("OMADA_USER", "lcastillo@cobeca.com")
OMADA_PASSWORD = os.environ.get("OMADA_PASSWORD", "Fu5@2026*.")
OMADA_SITE_NAME = os.environ.get("OMADA_SITE_NAME", "SAAS TROPICAL")

def get_db_connection():
    try:
        password = os.environ.get('DB_PASSWORD')
        if password:
            password = password.strip()  # Elimina espacios accidentales
            
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST', 'mysql.railway.internal'),
            user=os.environ.get('DB_USER', 'root'),
            password=password,
            database=os.environ.get('DB_NAME', 'railway'),
            port=3306,
            autocommit=True,
            defer_connect=False
        )
        return conn
    except Exception as e:
        print(f"Error conectando a MySQL interno: {e}")
        return None

def autorizar_en_omada_cloud(client_mac):
    if not OMADA_PASSWORD:
        print("Error crítico: La variable OMADA_PASSWORD no está definida en Railway.")
        return False
        
    try:
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })

        # Extraemos la raíz limpia del conector API
        base_url = OMADA_API_URL.split('/api')[0].rstrip('/')
        
        # 🎯 ENLACE DE LOGIN OFICIAL PARA CLOUD CONTROLLER CONNECTORS
        login_url = f"{base_url}/api/v1/login"
        login_payload = {
            "name": OMADA_USER,
            "password": OMADA_PASSWORD
        }
        
        print(f"Iniciando handshake en Conector Cloud de Omada: {login_url}")
        login_response = session.post(login_url, json=login_payload, timeout=10)
        
        # Manejo de fallback por si la cuenta está configurada en el árbol v2
        if login_response.status_code != 200 or "token" not in login_response.text:
            print("Handshake inicial V1 denegado o vacío. Intentando túnel V2 unificado...")
            login_url = f"{base_url}/v2/api/v1/login" if "/v2" not in base_url else f"{base_url}/api/v1/login"
            login_response = session.post(login_url, json=login_payload, timeout=10)

        if login_response.status_code != 200:
            print(f"Error de autenticación insalvable en la API de Omada ({login_response.status_code})")
            return False

        # Extracción e inspección limpia del payload de respuesta
        res_json = login_response.json()
        token = None
        if res_json and isinstance(res_json, dict):
            if "result" in res_json and isinstance(res_json["result"], dict):
                token = res_json["result"].get("token")
            else:
                token = res_json.get("token") or res_json.get("accessToken")

        if not token:
            token = login_response.headers.get("Comntoken") or login_response.headers.get("Token")

        if not token:
            print("Error analítico: Credenciales aceptadas pero no se localizó el token en el payload.")
            return False

        print("¡Conexión establecida con éxito! Token de seguridad enlazado.")
        
        # Inyección de headers globales requeridos para evitar el error de desconexión (-1200)
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "X-Auth-Token": token,
            "Comntoken": token
        })

        # --- PASO 2: OBTENER EL SITE ID ---
        # Aseguramos que la URL apunte al endpoint de control sobre el recurso controllers
        sites_url = f"{OMADA_API_URL}/sites"
        print(f"Buscando identificador para el sitio: {OMADA_SITE_NAME}")
        sites_response = session.get(sites_url, timeout=10)
        
        if sites_response.status_code != 200:
            print(f"Error al listar los recursos de sitios ({sites_response.status_code})")
            return False

        sites_data = sites_response.json()
        sites_list = []
        if isinstance(sites_data.get("result"), dict):
            sites_list = sites_data["result"].get("data", [])
        elif isinstance(sites_data.get("result"), list):
            sites_list = sites_data["result"]
        else:
            sites_list = sites_data.get("data", [])

        site_id = None
        for site in sites_list:
            if site.get("name") == OMADA_SITE_NAME:
                site_id = site.get("id")
                break

        if not site_id:
            print(f"Error: El sitio '{OMADA_SITE_NAME}' no fue encontrado en este controlador.")
            return False

        # --- PASO 3: AUTORIZAR LA MAC (CAMBIO DE ESTADO PENDING -> AUTHORIZED) ---
        # 🎯 IMPORTANTE: Para peticiones Cloud, se debe usar la ruta de comandos asíncronos 'cmd/authorizations'
        auth_url = f"{OMADA_API_URL}/sites/{site_id}/cmd/authorizations"
        
        # Normalizamos la MAC al formato estándar esperado por las tablas ARP de TP-Link (ej: 32-65-FC-B9-89-6D)
        formatted_mac = client_mac.replace(":", "-").upper()
        
        auth_payload = {
            "mac": formatted_mac,
            "action": 1,          # 1 = Conectar y liberar tráfico en el AP
            "duration": 1440      # Concesión por 24 horas (en minutos)
        }

        print(f"Enviando orden de cambio de estado a Omada para la MAC: {formatted_mac}")
        auth_response = session.post(auth_url, json=auth_payload, timeout=10)
        
        if auth_response.status_code == 200:
            auth_result = auth_response.json()
            # El código de éxito nativo de Omada es errorCode: 0
            if auth_result.get("errorCode") == 0 or auth_result.get("result") == "success":
                print(f"¡ÉXITO TOTAL! Dispositivo {formatted_mac} autorizado. Estado cambiado a CONNECTED.")
                return True
            else:
                print(f"La API del controlador rechazó la mutación de estado: {auth_result}")
                return False
        else:
            print(f"Error de comunicación en el puente de autorización ({auth_response.status_code}): {auth_response.text}")
            return False

    except Exception as e:
        print(f"Excepción general en el hilo de Omada Cloud: {e}")
        return False

# ==========================================
# RUTAS DE LA APLICACIÓN FLASK
# ==========================================

@app.route('/')
def index():
    return send_from_directory('.', 'registro.html')

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory('img', filename)

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    # 1. Recibir los datos del formulario HTML estándar
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    telefono = request.form.get('telefono')
    email = request.form.get('email')
    direccion = request.form.get('direccion')
    clientMac = request.form.get('clientMac')
    apMac = request.form.get('apMac')
    target = request.form.get('target')  # 🎯 Capturamos la URL destino original de Omada
    
    print(f"Procesando registro: nombre={nombre} {apellido}, MAC={clientMac}")

    # Validar campos obligatorios de datos personales
    if not all([nombre, apellido, telefono, email, direccion]):
        return "Faltan campos obligatorios", 400

    conn = get_db_connection()
    if not conn:
        return "Error de conexión con la base de datos", 500

    try:
        with conn.cursor() as cursor:
            # 2. Guardar en la tabla clientes de MySQL
            sql_cliente = """
                INSERT INTO clientes (nombre, apellido, telefono, email, direccion) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql_cliente, (nombre, apellido, telefono, email, direccion))
            
            # Obtener el ID autonumérico asignado
            id_usuario_nuevo = cursor.lastrowid
            print(f"Usuario guardado en MySQL con ID: {id_usuario_nuevo}")
            
            # 3. Guardar el registro histórico de fecha
            sql_fecha = "INSERT INTO fecha_registro (id_usuario_fr, fecha_registro) VALUES (%s, NOW())"
            cursor.execute(sql_fecha, (id_usuario_nuevo,))
            
        conn.close()
        
        # 4. SOLICITAR ACCESO A INTERNET A TRAVÉS DE LA MAC
        if clientMac:
            # Limpiar el formato de la MAC (ej: de 78-20-51... a 78:20:51...)
            mac_limpia = clientMac.replace("-", ":").strip().lower()
            print(f"Enviando orden de liberación remota para la MAC: {mac_limpia}")
            autorizar_en_omada_cloud(mac_limpia)
        else:
            print("Advertencia: No se recibió clientMac del formulario, no se puede liberar internet automáticamente.")
        
        # 5. REDIRECCIÓN EXITOSA DINÁMICA
        if target and target.strip():
            print(f"Redireccionando usuario al destino original: {target}")
            return redirect(target)
        else:
            print("No se detectó parámetro target. Redireccionando a Google por defecto.")
            return redirect("https://www.google.com")
        
    except Exception as e:
        print(f"Error durante el flujo de registro: {e}")
        if conn:
            conn.close()
        return "Error interno al procesar la solicitud", 500

if __name__ == '__main__':
    print("Servidor Flask de Producción Iniciado")
    # Controlamos el modo debug basándonos en variables de entorno para mayor seguridad
    modo_debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host='0.0.0.0', port=5000, debug=modo_debug)