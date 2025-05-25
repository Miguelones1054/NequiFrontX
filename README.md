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