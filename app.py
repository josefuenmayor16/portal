import os
import pymysql  # <- Cambiado a pymysql para interactuar con MySQL de Railway
from flask import Flask, request, jsonify, send_from_directory, redirect

app = Flask(__name__)

# Configura aquí los datos de tu Omada Cloud
OMADA_CONTROLLER_URL = "https://use1-omada-cloud.tplinkcloud.com"  # Dominio de la API de la nube
SITE_ID = "SAAS TROPICAL"   # Nombre del sitio extraído del panel

def get_db_connection():
    try:
        password = os.environ.get('DB_PASSWORD') or os.environ.get('MYSQLROOT_PASSWORD') or os.environ.get('MYSQLPASSWORD')
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST', 'mysql.railway.internal'),
            user=os.environ.get('DB_USER', 'root'),
            password=password,
            database=os.environ.get('DB_NAME', 'railway'),
            port=3306,
            autocommit=True  # Guarda los cambios de forma inmediata
        )
        return conn
    except Exception as e:
        print(f"Error conectando a MySQL interno: {e}")
        return None

@app.route('/')
def index():
    return send_from_directory('.', 'registro.html')

@app.route('/img/<path:filename>')
def serve_image(filename):
    return send_from_directory('img', filename)

@app.route('/api/registro', methods=['POST'])
def registro():
    conn = None
    try:
        data = request.json
        print(f"Datos recibidos: {data}")
        
        # Validar que todos los campos estén presentes
        required_fields = ['nombre', 'apellido', 'telefono', 'email', 'direccion']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'El campo {field} es obligatorio'}), 400
        
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
        
        # 1. Insertar en la tabla clientes (En MySQL la sintaxis usa %s)
        cursor.execute("""
            INSERT INTO clientes (nombre, apellido, telefono, email, direccion)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, apellido, telefono, email, direccion))
        
        # 2. Obtener el ID generado (En MySQL usamos cursor.lastrowid en lugar de SCOPE_IDENTITY)
        id_usuario = cursor.lastrowid
        print(f"ID de usuario generado en Railway: {id_usuario}")
        
        # 3. Insertar en la tabla fecha_registro (Cambiado GETDATE() por NOW() que es el nativo de MySQL)
        cursor.execute("""
            INSERT INTO fecha_registro (id_usuario_fr, fecha_registro)
            VALUES (%s, NOW())
        """, (id_usuario,))
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'Usuario registrado exitosamente en la nube',
            'id_usuario': id_usuario
        }), 201
        
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.close()
        return jsonify({'error': f'Error en la base de datos: {str(e)}'}), 500

@app.route('/registrar', methods=['POST'])
def registrar_usuario():
    # 1. Recibir los datos del formulario HTML
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    telefono = request.form.get('telefono')
    email = request.form.get('email')
    direccion = request.form.get('direccion')
    clientMac = request.form.get('clientMac')
    apMac = request.form.get('apMac')
    
    print(f"Datos del formulario: nombre={nombre}, apellido={apellido}, clientMac={clientMac}, apMac={apMac}")

    # Validar campos obligatorios
    if not all([nombre, apellido, telefono, email, direccion]):
        return "Faltan campos obligatorios", 400

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # 2. Insertar en la tabla clientes (fíjate en las minúsculas y los %s)
                sql_cliente = """
                    INSERT INTO clientes (nombre, apellido, telefono, email, direccion) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql_cliente, (nombre, apellido, telefono, email, direccion))
                
                # Obtener el ID recién creado
                id_usuario_nuevo = cursor.lastrowid
                print(f"ID de usuario generado: {id_usuario_nuevo}")
                
                # 3. Insertar el registro de fecha
                sql_fecha = "INSERT INTO fecha_registro (id_usuario_fr, fecha_registro) VALUES (%s, NOW())"
                cursor.execute(sql_fecha, (id_usuario_nuevo,))
                
            conn.close()
            
            # 2. CAPTURAR EL PARÁMETRO DE REDIRECCIÓN DE OMADA
            # Cuando Omada abre el portal, envía una variable en la URL llamada 'target' 
            # que contiene la dirección exacta del controlador en la nube para autorizar el dispositivo.
            target_url = request.args.get('target') or request.form.get('target')
            
            if target_url:
                print(f"Redirigiendo cliente a Omada Cloud para liberar internet: {target_url}")
                # Al mandar al usuario al target, el navegador del cliente ejecuta la autorización 
                # directamente contra la nube de TP-Link de manera transparente.
                return redirect(target_url)
            else:
                # Si por alguna razón el target no vino (ej. pruebas manuales), 
                # lo mandamos a Google para que no se quede colgado en pantalla blanca.
                print("No se detectó parámetro target, enviando a Google por defecto.")
                return redirect("https://www.google.com")
            
        except Exception as e:
            print(f"Error durante el registro en la BD: {e}")
            if conn:
                conn.close()
            return "Error interno al guardar los datos", 500
    else:
        return "Error de conexión con la base de datos", 500

if __name__ == '__main__':
    # Cambiado a puerto 5000 para que machee perfectamente con tu configuración de Omada
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)