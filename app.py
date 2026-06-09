import os
import pymysql
import requests
import urllib3
from flask import Flask, request, redirect, send_from_directory

# Deshabilitar advertencias de certificados auto-firmados del OC300
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Configuración obligatoria apuntando directamente a tu controlador OC300 local
OMADA_CONTROLLER_URL = os.environ.get("OMADA_CONTROLLER_URL", "https://172.172.1.30:8043")
OMADA_USER = os.environ.get("OMADA_USER", "lcastillo@cobeca.com")
OMADA_PASSWORD = os.environ.get("OMADA_PASSWORD", "Fu5@2026*.")
OMADA_SITE_NAME = os.environ.get("OMADA_SITE_NAME", "SAAS TROPICAL")

# Cache global para optimizar el performance
cached_omada_token = None
cached_site_id = None

def get_db_connection():
    try:
        password = os.environ.get('DB_PASSWORD')
        if password:
            password = password.strip()
            
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

def autorizar_en_omada_local(client_mac):
    global cached_omada_token, cached_site_id
    
    base_url = OMADA_CONTROLLER_URL.rstrip('/')
    formatted_mac = client_mac.replace(":", "-").replace(" ", "").upper()
    
    session = requests.Session()
    # Ignorar la verificación SSL ya que el OC300 local suele usar un certificado auto-firmado
    session.verify = False 
    
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json"
    })

    try:
        # --- PASO 1: LOGIN Y OBTENCIÓN DEL TOKEN ---
        if cached_omada_token:
            token = cached_omada_token
            print(f"Usando token local cacheado: {token[:8]}...")
        else:
            login_url = f"{base_url}/api/v2/login"  # Forzamos API v2 compatible con OC300 actualizados
            login_payload = {
                "username": OMADA_USER,
                "password": OMADA_PASSWORD
            }
            
            print(f"Iniciando sesión en OC300 Local: {login_url}")
            login_response = session.post(login_url, json=login_payload, timeout=8)
            
            if login_response.status_code != 200:
                print(f"Fallo de login en OC300 (Status: {login_response.status_code}). Revisar credenciales.")
                return False
                
            res_json = login_response.json()
            token = None
            if res_json and isinstance(res_json, dict):
                if "result" in res_json and isinstance(res_json["result"], dict):
                    token = res_json["result"].get("token")
            
            if not token:
                print(f"No se pudo extraer el token del OC300. Respuesta: {res_json}")
                return False
                
            cached_omada_token = token
            print(f"¡Token local generado con éxito!: {token[:8]}...")

        # Inyectar el token en la cabecera estándar de Omada local
        session.headers.update({"Csrf-Token": token})
        # Los controladores físicos manejan cookies de sesión tras el login
        
        # --- PASO 2: OBTENER EL SITE ID ---
        if cached_site_id:
            site_id = cached_site_id
        else:
            sites_url = f"{base_url}/api/v2/sites"
            sites_response = session.get(sites_url, timeout=8)
            
            if sites_response.status_code != 200:
                print(f"Error recuperando sitios del OC300: {sites_response.text}")
                # Resetear cache del token por si caducó
                cached_omada_token = None
                return False
                
            sites_data = sites_response.json()
            sites_list = []
            if isinstance(sites_data.get("result"), dict):
                sites_list = sites_data["result"].get("data", [])
            else:
                sites_list = sites_data.get("result", [])
                
            site_id = None
            for site in sites_list:
                if site.get("name") == OMADA_SITE_NAME:
                    site_id = site.get("id")
                    break
                    
            if not site_id:
                print(f"No se encontró el sitio '{OMADA_SITE_NAME}' en el OC300.")
                return False
                
            cached_site_id = site_id
            print(f"Identificado Site ID Local: {site_id}")

        # --- PASO 3: ENVIAR COMANDO DE AUTORIZACIÓN ---
        auth_url = f"{base_url}/api/v2/sites/{site_id}/cmd/authorizations"
        auth_payload = {
            "mac": formatted_mac,
            "action": 1,          # 1 = Autorizar acceso
            "duration": 1440      # 24 horas en minutos
        }
        
        print(f"Liberando internet en OC300 para la MAC [{formatted_mac}]")
        auth_response = session.post(auth_url, json=auth_payload, timeout=8)
        
        if auth_response.status_code == 200:
            auth_result = auth_response.json()
            if auth_result.get("errorCode") == 0:
                print(f"¡ÉXITO LOCAL! Dispositivo {formatted_mac} autorizado en el OC300.")
                return True
            else:
                print(f"El OC300 denegó la autorización: {auth_result}")
                # Si el error es de sesión expirada, limpiamos el caché para reintentar en la próxima
                if auth_result.get("errorCode") in [-1000, -1005, -1200]:
                    cached_omada_token = None
                return False
        else:
            print(f"Error HTTP en comando de autorización ({auth_response.status_code}): {auth_response.text}")
            cached_omada_token = None
            return False

    except Exception as e:
        print(f"Excepción en comunicación local con el OC300: {e}")
        cached_omada_token = None
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
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    telefono = request.form.get('telefono')
    email = request.form.get('email')
    direccion = request.form.get('direccion')
    clientMac = request.form.get('clientMac')
    apMac = request.form.get('apMac')
    target = request.form.get('target')
    
    print(f"DEBUG - Todos los parámetros recibidos: {dict(request.form)}")
    print(f"Procesando registro: nombre={nombre} {apellido}, MAC={clientMac}, AP_MAC={apMac}, target={target}")

    if not all([nombre, apellido, telefono, email, direccion]):
        return "Faltan campos obligatorios", 400

    conn = get_db_connection()
    if not conn:
        return "Error de conexión con la base de datos", 500

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
        
        # RUTA ÓPTIMA PARA AUTORIZACIÓN OMADA
        if clientMac and apMac:
            # MÉTODO PRIMARIO: Redirección local al controlador (recomendado por TP-Link)
            html_auth = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Conectando...</title>
                <meta charset="UTF-8">
            </head>
            <body>
                <p>Autorizando acceso a Internet, por favor espere...</p>
                
                <form id="omadaAuthForm" action="http://172.172.1.30:8088/portal/auth" method="get">
                    <input type="hidden" name="clientMac" value="{clientMac}">
                    <input type="hidden" name="apMac" value="{apMac}">
                </form>

                <script>
                    window.onload = function() {{
                        document.getElementById('omadaAuthForm').submit();
                    }};
                </script>
            </body>
            </html>
            """
            print(f"Redirección al controlador Omada para conectar a PRUEBAS SAAS: MAC={clientMac}")
            return html_auth, 200
        elif clientMac:
            # MÉTODO SECUNDARIO: API Local (fallback si no hay apMac)
            mac_limpia = clientMac.replace("-", ":").strip().lower()
            print(f"Usando API Local para autorizar MAC: {mac_limpia}")
            autorizar_en_omada_local(mac_limpia)
            
            redirect_to = target if (target and target.strip()) else "https://www.google.com"
            return redirect(redirect_to)
        else:
            print("Advertencia: No se recibió clientMac, no se puede autorizar automáticamente.")
            redirect_to = target if (target and target.strip()) else "https://www.google.com"
            return redirect(redirect_to)
        
    except Exception as e:
        print(f"Error durante el flujo de registro: {e}")
        if conn:
            conn.close()
        return "Error interno al procesar la solicitud", 500

if __name__ == '__main__':
    print("Servidor Flask de Production Iniciado")
    modo_debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host='0.0.0.0', port=5000, debug=modo_debug)