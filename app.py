from flask import Flask, request, jsonify, send_from_directory
import pypyodbc

app = Flask(__name__)

# Configuración de la conexión a SQL Server
def get_db_connection():
    server = r'USER\PASANTE'
    database = 'portal'
    driver = '{ODBC Driver 17 for SQL Server}'
    
    # Usar autenticación de Windows (Integrated Security)
    conn_str = f'DRIVER={driver};SERVER={server};DATABASE={database};Trusted_Connection=yes'
    
    try:
        conn = pypyodbc.connect(conn_str)
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
        
        # Insertar en la tabla clientes
        cursor.execute("""
            INSERT INTO dbo.clientes (nombre, apellido, telefono, email, direccion)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre, apellido, telefono, email, direccion))
        print("Datos insertados en tabla clientes")
        
        # Obtener el ID del usuario insertado
        cursor.execute("SELECT SCOPE_IDENTITY() as id_usuario")
        id_usuario = cursor.fetchone()[0]
        print(f"ID de usuario generado: {id_usuario}")
        
        # Insertar en la tabla fecha_registro
        cursor.execute("""
            INSERT INTO dbo.fecha_registro (id_usuario_fr, fecha_registro)
            VALUES (?, GETDATE())
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
    print("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
