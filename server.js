const express = require('express');
const sql = require('mssql');
const cors = require('cors');
const bodyParser = require('body-parser');

const app = express();
const PORT = 5000;

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(express.static(__dirname));

// Configuración de la conexión a SQL Server
const config = {
    server: 'localhost',
    database: 'portal',
    user: 'sa',
    password: '',
    options: {
        encrypt: true,
        trustServerCertificate: true,
        enableArithAbort: true
    }
};

// Función para conectar a la base de datos
async function connectToDatabase() {
    try {
        await sql.connect(config);
        console.log('Conectado a la base de datos SQL Server');
    } catch (err) {
        console.error('Error al conectar a la base de datos:', err);
    }
}

// Ruta para el registro de usuarios
app.post('/api/registro', async (req, res) => {
    try {
        const { nombre, apellido, telefono, email, direccion } = req.body;
        
        // Validar que todos los campos estén presentes
        if (!nombre || !apellido || !telefono || !email || !direccion) {
            return res.status(400).json({ error: 'Todos los campos son obligatorios' });
        }
        
        // Crear pool de conexión
        const pool = await sql.connect(config);
        
        // Insertar el nuevo usuario en la tabla clientes
        const result = await pool.request()
            .input('nombre', sql.VarChar(30), nombre)
            .input('apellido', sql.VarChar(30), apellido)
            .input('telefono', sql.VarChar(25), telefono)
            .input('email', sql.VarChar(50), email)
            .input('direccion', sql.VarChar(50), direccion)
            .query(`
                INSERT INTO dbo.clientes (nombre, apellido, telefono, email, direccion)
                VALUES (@nombre, @apellido, @telefono, @email, @direccion);
                SELECT SCOPE_IDENTITY() as id_usuario;
            `);
        
        // Obtener el ID del usuario insertado
        const idUsuario = result.recordset[0].id_usuario;
        
        // Insertar el registro de fecha
        await pool.request()
            .input('id_usuario_fr', sql.Int, idUsuario)
            .query(`
                INSERT INTO dbo.fecha_registro (id_usuario_fr, fecha_registro)
                VALUES (@id_usuario_fr, GETDATE());
            `);
        
        await pool.close();
        
        res.status(201).json({ 
            message: 'Usuario registrado exitosamente',
            id_usuario: idUsuario 
        });
        
    } catch (err) {
        console.error('Error al registrar usuario:', err);
        res.status(500).json({ error: 'Error al registrar usuario en la base de datos' });
    }
});

// Ruta para servir el archivo HTML
app.get('/', (req, res) => {
    res.sendFile(__dirname + '/registro.html');
});

// Iniciar el servidor
app.listen(PORT, async () => {
    console.log(`Servidor corriendo en http://localhost:${PORT}`);
    await connectToDatabase();
});
