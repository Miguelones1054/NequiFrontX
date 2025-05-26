# API de Generación de Imágenes Nequi

API para generar imágenes de comprobantes de Nequi.

## Características

- Genera imágenes de comprobantes tipo voucher
- Genera imágenes de detalles de movimientos
- Formatea automáticamente valores monetarios
- Formatea automáticamente números de teléfono
- Genera automáticamente fechas y códigos de referencia

## Uso

### Endpoint principal

```
POST /generate_image/
```

### Ejemplo de solicitud

```json
{
  "tipo": "voucher",
  "datos": {
    "recipient": "Samuel Quintero",
    "amount": "1000000",
    "phone": "3141234567"
  }
}
```

### Respuesta

La API responde con una imagen JPEG.

## Desarrollo local

1. Instalar dependencias:
```
pip install -r requirements.txt
```

2. Iniciar servidor de desarrollo:
```
uvicorn main:app --reload
```

## Producción

1. Usar Gunicorn como servidor WSGI:
```
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

## Push a GitHub

Para subir los cambios a GitHub, sigue estos comandos en orden:

```bash
# Agregar todos los archivos modificados al stage
git add .

# Crear un commit con un mensaje descriptivo
git commit -m "Descripción de los cambios realizados"

# Subir los cambios al repositorio remoto (rama principal)
git push origin main
```

Para configurar un repositorio por primera vez:

```bash
# Inicializar repositorio Git local
git init

# Agregar un repositorio remoto
git remote add origin https://github.com/usuario/repo.git

# Agregar todos los archivos
git add .

# Hacer el primer commit
git commit -m "Commit inicial"

# Subir al repositorio remoto
git push -u origin main
``` 