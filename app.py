import os
from flask import Flask, request, jsonify, send_from_directory
import pypyodbc
import requests
import urllib3

# Deshabilitar advertencias de certificados autofirmados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Configuración de la conexión a SQL Server
def get_db_connection():
    server = os.getenv('DB_SERVER', r'USER\PASANTE')
    database = os.getenv('DB_NAME', 'portal')
    driver = '{ODBC Driver 17 for SQL Server}'
    
    # Usar autenticación de Windows (Integrated Security)
    conn_str = f'DRIVER={driver};SERVER={server};DATABASE={database};Trusted_Connection=yes'
    
    try:
        conn = pypyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
        return None

# Caché global para el token de Omada
omada_token_cache = {"token": None}

def authorize_omada_client(client_mac, ap_mac, retry=True):
    """
    Se conecta al controlador Omada para autorizar a un cliente.
    Optimizado con caché de token para evitar login en cada registro.
    """
    omada_url = os.getenv('OMADA_URL', 'https://172.172.1.30:8043')
    username = os.getenv('OMADA_USERNAME', 'admin')
    password = os.getenv('OMADA_PASSWORD', 'admin')
    
    session = requests.Session()
    
    try:
        # Si no hay token en caché, hacemos login
        if not omada_token_cache["token"]:
            login_url = f"{omada_url}/api/v2/login"
            login_data = {"username": username, "password": password}
            
            print(f"Intentando login en Omada: {login_url}")
            response = session.post(login_url, json=login_data, verify=False, timeout=30)
            response.raise_for_status()
            
            login_result = response.json()
            token = login_result.get('result', {}).get('token')
            
            if not token:
                print("Error: No se pudo obtener el token de Omada.")
                return False
            
            omada_token_cache["token"] = token
        
        # Autorizar el cliente con el token (en caché o recién obtenido)
        token = omada_token_cache["token"]
        headers = {'Csrf-Token': token}
        
        auth_url = f"{omada_url}/api/v2/hotspot/login" # Ajustar según API real
        auth_data = {
            "clientMac": client_mac,
            "apMac": ap_mac
        }
        
        print(f"Autorizando cliente en Omada: {client_mac}")
        auth_resp = session.post(auth_url, json=auth_data, headers=headers, verify=False, timeout=30)
        
        # Si el token expiró o es inválido, Omada suele devolver un 401 o 403, 
        # o un JSON con código de error. Verificamos si falló por autenticación.
        if auth_resp.status_code in (401, 403) and retry:
            print("Token expirado o inválido, reintentando login...")
            omada_token_cache["token"] = None
            return authorize_omada_client(client_mac, ap_mac, retry=False)
            
        auth_resp.raise_for_status()
        
        print("Cliente autorizado exitosamente en Omada.")
        return True
        
    except requests.exceptions.Timeout:
        print("Timeout al conectar con Omada Controller.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error de red/API al conectar con Omada Controller: {e}")
        # Si hubo error de red, podríamos borrar el token por si el server se reinició
        if retry:
            omada_token_cache["token"] = None
            return authorize_omada_client(client_mac, ap_mac, retry=False)
        return False
    except Exception as e:
        print(f"Error inesperado al conectar con Omada: {e}")
        return False
    finally:
        session.close()

@app.route('/')
def index():
    return send_from_directory('.', 'registro.html')

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory('img', filename)

@app.route('/api/registro', methods=['POST'])
def registro():
    conn = None
    cursor = None
    try:
        data = request.json
        print(f"Datos recibidos: {data}")
        
        # Validar que todos los campos estén presentes
        required_fields = ['nombre', 'apellido', 'telefono', 'email', 'direccion']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'El campo {field} es obligatorio'}), 400
        
        # Parámetros Omada
        client_mac = data.get('clientMac')
        ap_mac = data.get('apMac')
        
        nombre = data['nombre']
        apellido = data['apellido']
        telefono = data['telefono']
        email = data['email']
        direccion = data['direccion']
        
        # Conectar a la base de datos
        conn = get_db_connection()
        if not conn:
            print("Error: No se pudo conectar a la base de datos")
            return jsonify({'error': 'Error de conexión a la base de datos'}), 500
        
        cursor = conn.cursor()
        print("Conexión exitosa, insertando datos...")
        
        # Insertar en la tabla clientes
        cursor.execute("""
            INSERT INTO dbo.clientes (nombre, apellido, telefono, email, direccion)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre, apellido, telefono, email, direccion))
        print("Datos insertados en tabla clientes")
        
        # Obtener el ID del usuario insertado de manera segura
        cursor.execute("SELECT @@IDENTITY AS id_usuario")
        row = cursor.fetchone()
        id_usuario = int(row[0]) if row and row[0] else None
        print(f"ID de usuario generado: {id_usuario}")
        
        if id_usuario:
            # Insertar en la tabla fecha_registro
            cursor.execute("""
                INSERT INTO dbo.fecha_registro (id_usuario_fr, fecha_registro)
                VALUES (?, GETDATE())
            """, (id_usuario,))
            print("Datos insertados en tabla fecha_registro")
            
            conn.commit()
            print("Transacción confirmada (commit)")
        else:
            conn.rollback()
            raise Exception("No se pudo obtener el ID del usuario insertado.")
        
        # Autorizar en Omada si se tienen las MACs
        omada_authorized = False
        if client_mac and ap_mac:
            omada_authorized = authorize_omada_client(client_mac, ap_mac)
            if not omada_authorized:
                print("Advertencia: Falló la autorización en Omada.")
        else:
            print("Advertencia: No se proporcionaron clientMac o apMac. Se omitirá la autorización de Omada.")
            
        return jsonify({
            'message': 'Usuario registrado exitosamente',
            'id_usuario': id_usuario,
            'omada_authorized': omada_authorized
        }), 201
        
    except Exception as e:
        print(f"Error al registrar usuario: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al registrar usuario en la base de datos: {str(e)}'}), 500
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

if __name__ == '__main__':
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
