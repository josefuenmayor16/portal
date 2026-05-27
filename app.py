import os
import pymysql  # <- Cambiado a pymysql para interactuar con MySQL de Railway
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

def get_db_connection():
    try:
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            database=os.environ.get('DB_NAME'),
            port=3306,
            autocommit=True # Guarda los cambios automáticamente
        )
        return conn
    except Exception as e:
        print(f"Error conectando a la base de datos interna: {e}")
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

if __name__ == '__main__':
    # Cambiado a puerto 5000 para que machee perfectamente con tu configuración de Omada
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)