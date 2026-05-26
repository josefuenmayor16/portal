from flask import Flask, request, jsonify, send_from_directory
import pymssql  # <- Cambiado pypyodbc por pymssql

app = Flask(__name__)

# Configuración de la conexión a SQL Server externa
def get_db_connection():
    # NOTA: En Railway debes usar la IP pública o el Hostname de donde esté alojado tu SQL Server
    # No olvides abrir el puerto 1433 en el firewall de tu servidor de base de datos.
    server = r'USER\PASANTE' 
    database = 'portal'

    
    try:
        # pymssql se conecta directo usando las credenciales SQL
        conn = pymssql.connect(
            server=server, 
            database=database,
            port=1433 # Puerto por defecto de SQL Server
        )
        return conn
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
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
        
        # 1. Insertar en la tabla clientes (Cambiado '?' por '%s')
        cursor.execute("""
            INSERT INTO dbo.clientes (nombre, apellido, telefono, email, direccion)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, apellido, telefono, email, direccion))
        print("Datos insertados en tabla clientes")
        
        # 2. Obtener el ID del usuario insertado
        # NOTA: SCOPE_IDENTITY() requiere ejecutar un SELECT inmediatamente después del INSERT 
        # en la misma sesión/cursor.
        cursor.execute("SELECT SCOPE_IDENTITY() as id_usuario")
        id_usuario = cursor.fetchone()[0]
        print(f"ID de usuario generado: {id_usuario}")
        
        # 3. Insertar en la tabla fecha_registro (Cambiado '?' por '%s')
        cursor.execute("""
            INSERT INTO dbo.fecha_registro (id_usuario_fr, fecha_registro)
            VALUES (%s, GETDATE())
        """, (id_usuario,))
        print("Datos insertados en tabla fecha_registro")
        
        conn.commit()
        print("Transacción confirmada (commit)")
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'Usuario registrado exitosamente',
            'id_usuario': id_usuario
        }), 201
        
    except Exception as e:
        print(f"Error al registrar usuario: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({'error': f'Error al registrar usuario en la base de datos: {str(e)}'}), 500

if __name__ == '__main__':
    # Cambiado a puerto 5000 para que machee perfectamente con tu configuración de Omada
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)