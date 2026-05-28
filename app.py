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
            "Accept": "application/json"
        })

        # Limpiamos la URL para evitar duplicaciones
        base_url = OMADA_API_URL.split('/api')[0].rstrip('/')
        
        # 🎯 Endpoint estándar para controladoras en Omada Cloud
        login_url = f"{base_url}/api/v1/login"
        
        print(f"Intentando inicio de sesión en Omada Cloud: {login_url}")
        login_payload = {
            "name": OMADA_USER,       # Nota: Algunas versiones de la API v1 piden 'name' en lugar de 'username'
            "password": OMADA_PASSWORD
        }
        
        login_response = session.post(login_url, json=login_payload, timeout=10)
        
        # Si falla, intentamos con el formato alternativo tradicional
        if login_response.status_code != 200:
            print(f"Fallo inicial con 'name' ({login_response.status_code}). Probando con 'username'...")
            login_url = f"{base_url}/api/login"
            login_payload = {"username": OMADA_USER, "password": OMADA_PASSWORD}
            login_response = session.post(login_url, json=login_payload, timeout=10)

        if login_response.status_code != 200:
            print(f"Error crítico en Omada Login ({login_response.status_code}): {login_response.text[:200]}")
            return False
            
        login_data = login_response.json()
        token = login_data.get("result", {}).get("token")
        
        if not token:
            print(f"No se pudo extraer el token de la respuesta: {login_data}")
            return False
            
        print("¡Sesión iniciada con éxito! Token obtenido.")
        
        # Cabecera de autorización para los siguientes pasos
        headers = {"Authorization": f"Bearer {token}"}
        api_v1_url = f"{base_url}/api/v1"
        
        # 2. Obtener el Site ID usando el nombre "SAAS TROPICAL"
        sites_url = f"{api_v1_url}/sites"
        sites_response = session.get(sites_url, headers=headers, timeout=10)
        sites_data = sites_response.json()
        
        site_id = None
        for site in sites_data.get("result", {}).get("data", []):
            if site.get("name") == OMADA_SITE_NAME:
                site_id = site.get("id")
                break
                
        if not site_id:
            print(f"No se encontró el sitio: {OMADA_SITE_NAME}")
            return False

        # 3. Autorizar la MAC del usuario
        auth_url = f"{api_v1_url}/sites/{site_id}/cmd/authorizations"
        auth_payload = {
            "mac": client_mac,
            "action": 1,          # 1 = Autorizar / Conectar
            "duration": 1440      # 24 horas
        }
        
        auth_response = session.post(auth_url, json=auth_payload, headers=headers, timeout=10)
        auth_result = auth_response.json()
        
        if auth_response.status_code == 200 and auth_result.get("errorCode") == 0:
            print(f"¡ÉXITO APOTEÓSICO! Dispositivo {client_mac} autorizado en Omada.")
            return True
        else:
            print(f"Omada rechazó la liberación de la MAC: {auth_result}")
            return False
            
    except Exception as e:
        print(f"Fallo crítico inesperado en Omada Cloud: {e}")
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