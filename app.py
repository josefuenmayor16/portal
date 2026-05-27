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
OMADA_PASSWORD = os.environ.get("OMADA_PASSWORD")
OMADA_SITE_NAME = os.environ.get("OMADA_SITE_NAME", "SAAS TROPICAL")

def get_db_connection():
    try:
        password = os.environ.get('DB_PASSWORD')
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST', 'mysql.railway.internal'),
            user=os.environ.get('DB_USER', 'root'),
            password=password,
            database=os.environ.get('DB_NAME', 'railway'),
            port=3306,
            autocommit=True,
            # 🔑 Solución al Error 500: Obliga a usar el método compatible con cryptography
            auth_plugin='caching_sha256_password'
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
        # 1. Iniciar sesión en la API de Omada Cloud para obtener el Token
        print(f"Iniciando sesión en Omada Cloud para el usuario: {OMADA_USER}...")
        login_url = f"{OMADA_API_URL}/login"
        login_payload = {
            "username": OMADA_USER,
            "password": OMADA_PASSWORD
        }
        
        session = requests.Session()
        login_response = session.post(login_url, json=login_payload, timeout=7)
        login_data = login_response.json()
        
        if login_response.status_code != 200 or not login_data.get("result"):
            print(f"Error de autenticación en Omada Cloud: {login_data}")
            return False
            
        token = login_data["result"]["token"]
        
        # 2. Obtener el Site ID usando el nombre "SAAS TROPICAL"
        sites_url = f"{OMADA_API_URL}/sites"
        headers = {"Authorization": f"Bearer {token}"}
        sites_response = session.get(sites_url, headers=headers, timeout=7)
        sites_data = sites_response.json()
        
        site_id = None
        for site in sites_data.get("result", {}).get("data", []):
            if site.get("name") == OMADA_SITE_NAME:
                site_id = site.get("id")
                break
                
        if not site_id:
            print(f"No se encontró ningún sitio con el nombre: {OMADA_SITE_NAME}")
            return False

        # 3. Autorizar la MAC del usuario para otorgarle Internet
        auth_url = f"{OMADA_API_URL}/sites/{site_id}/cmd/authorizations"
        auth_payload = {
            "mac": client_mac,
            "action": 1,          # 1 = Conectar / Autorizar
            "duration": 1440      # 24 horas de navegación libre
        }
        
        auth_response = session.post(auth_url, json=auth_payload, headers=headers, timeout=7)
        auth_result = auth_response.json()
        
        if auth_response.status_code == 200 and auth_result.get("errorCode") == 0:
            print(f"¡ÉXITO! Dispositivo {client_mac} autorizado correctamente en Omada Cloud.")
            return True
        else:
            print(f"Omada Cloud rechazó la autorización de la MAC: {auth_result}")
            return False
            
    except Exception as e:
        print(f"Fallo crítico en la comunicación con Omada Cloud: {e}")
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
        
        # 5. REDIRECCIÓN EXITOSA
        return redirect("https://www.google.com")
        
    except Exception as e:
        print(f"Error durante el flujo de registro: {e}")
        if conn:
            conn.close()
        return "Error interno al procesar la solicitud", 500

if __name__ == '__main__':
    print("Servidor Flask de Producción Iniciado")
    app.run(host='0.0.0.0', port=5000, debug=True)