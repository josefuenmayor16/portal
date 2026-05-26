# Sistema de Registro de Usuarios

Sistema de registro de usuarios conectado a base de datos SQL Server usando Python/Flask.

## Estructura de la Base de Datos

### Tabla: clientes
- `id_usuario` (int, PK, Identity)
- `nombre` (varchar(30))
- `apellido` (varchar(30))
- `telefono` (varchar(25))
- `email` (varchar(50))
- `direccion` (varchar(50))

### Tabla: fecha_registro
- `id_registro` (int, PK, Identity)
- `id_usuario_fr` (int, FK)
- `fecha_registro` (datetime, default: GETDATE())

## Instalación

1. Asegúrate de tener Python 3 instalado en tu sistema

2. Instala las dependencias:
```bash
pip install -r requirements.txt
```

3. Configura la conexión a la base de datos en `app.py`:
   - Actualiza el campo `password` con tu contraseña de SQL Server (línea 12)
   - Si tu servidor no es localhost, actualiza el campo `server` (línea 9)
   - Asegúrate de tener el driver ODBC para SQL Server instalado

## Ejecución

Inicia el servidor:
```bash
python app.py
```

El servidor estará disponible en: http://localhost:3000

## Uso

1. Abre tu navegador y ve a http://localhost:3000
2. Completa el formulario de registro con:
   - Nombre
   - Apellido
   - Número Telefónico
   - Correo Electrónico
   - Dirección (Aprox)
3. Haz clic en "Registrarse"
4. Los datos se guardarán en la base de datos `portal`

## Notas Importantes

- Asegúrate de que SQL Server esté corriendo antes de iniciar el servidor
- La base de datos `portal` debe existir (puedes crearla ejecutando el script `portal.sql`)
- Verifica que el usuario de SQL Server tenga los permisos necesarios para insertar datos
- Necesitas tener el driver ODBC para SQL Server instalado (ODBC Driver 17 for SQL Server)
