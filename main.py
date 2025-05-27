from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import json
import os
from datetime import datetime, timedelta
import locale
import random
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pytz  # Importar pytz para manejar zonas horarias
import unicodedata  # Para normalizar caracteres
from collections import defaultdict
import firebase_admin
from firebase_admin import auth, credentials

# Inicializar Firebase
cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)

# Configurar locale para español
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'es')
        except locale.Error:
            # Si falla, usar el locale por defecto
            pass

# Definir la zona horaria de Colombia
colombia_tz = pytz.timezone('America/Bogota')

app = FastAPI()

# Definir directorios base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
COORDS_DIR = os.path.join(BASE_DIR, "cordenadas")

# Montar directorio de archivos estáticos
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "assets")), name="static")

# Configurar templates
templates = Jinja2Templates(directory=BASE_DIR)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas las origenes
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos
    allow_headers=["*"],  # Permite todas las cabeceras
)

# Diccionario para almacenar las peticiones por IP
request_counts = defaultdict(lambda: {"count": 0, "reset_time": datetime.now() + timedelta(minutes=1)})

# Función para verificar el rate limit
def check_rate_limit(ip: str) -> bool:
    current_time = datetime.now()
    
    # Si el tiempo de reset ha pasado, reiniciar el contador
    if current_time > request_counts[ip]["reset_time"]:
        request_counts[ip] = {"count": 0, "reset_time": current_time + timedelta(minutes=1)}
    
    # Incrementar el contador
    request_counts[ip]["count"] += 1
    
    # Verificar si se excedió el límite (ahora 10 peticiones por minuto)
    return request_counts[ip]["count"] <= 10

# Función para verificar el token de Firebase
async def verify_firebase_token(request: Request) -> str:
    # Obtener el token del header Authorization
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="TE PAGO UN CURSO DE DE SEGURIDAD XD"
        )
    
    # Extraer el token
    token = auth_header.split("Bearer ")[1]
    
    try:
        # Verificar el token con Firebase
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']  # Retornar el ID del usuario
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado"
        )

class Data(BaseModel):
    recipient: str
    amount: str
    phone: str = ""  # Ahora es opcional para los tipos QR
    mvalue: str = ""  # Valor proporcionado por el usuario, se añadirá "M" si es necesario
    disponible: str = "Disponible"  # Valor por defecto, se sobreescribirá

class ImageRequest(BaseModel):
    tipo: str
    datos: Data

def normalizar_texto(texto):
    # Convertir a string si no lo es
    texto = str(texto)
    # Normalizar caracteres Unicode (NFKD) y eliminar diacríticos
    texto = unicodedata.normalize('NFKD', texto)
    # Reemplazar ñ por n
    texto = texto.replace('ñ', 'n').replace('Ñ', 'N')
    # Eliminar caracteres no ASCII
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Obtener la hora actual en Colombia para mostrarla en la página
    now = datetime.now(colombia_tz)
    current_time = now.strftime("%d/%m/%Y %H:%M:%S")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Nequi Generator</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background-color: #DA0081;
                color: white;
                text-align: center;
            }}
            .container {{
                max-width: 800px;
                padding: 20px;
                background-color: rgba(0, 0, 0, 0.1);
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            }}
            h1 {{
                font-size: 2.5em;
                margin-bottom: 20px;
            }}
            p {{
                font-size: 1.2em;
                line-height: 1.6;
                margin-bottom: 15px;
            }}
            .status {{
                display: inline-block;
                padding: 8px 16px;
                background-color: #4CAF50;
                border-radius: 4px;
                font-weight: bold;
                margin-top: 20px;
            }}
            .time {{
                margin-top: 15px;
                font-size: 0.9em;
                opacity: 0.8;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>API de Generación de Imágenes Nequi</h1>
            <p>Esta API permite generar imágenes de comprobantes de pago y detalles de movimientos en formato Nequi.</p>
            <p>Para usar la API, envía solicitudes POST al endpoint /generate_image/ con los parámetros requeridos.</p>
            <div class="status">Estado: Activo</div>
            <div class="time">Hora Colombia: {current_time}</div>
        </div>
    </body>
    </html>
    """
    
    # Para solicitudes GET, devuelve la página HTML
    return HTMLResponse(content=html_content)

@app.head("/")
async def read_root_head():
    # Para solicitudes HEAD, simplemente devuelve un código 200 sin contenido
    return Response(status_code=200)

@app.post("/generate_image/")
async def generate_image(request: ImageRequest, request_obj: Request):
    # Verificar autenticación
    user_id = await verify_firebase_token(request_obj)
    
    # Obtener la IP del cliente
    client_ip = request_obj.client.host if request_obj.client else "unknown"
    
    # Verificar rate limit
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor: No se pudo procesar la solicitud en este momento. Por favor, intente más tarde."
        )
    
    # Base paths con rutas relativas desde el directorio base
    image_base_path = os.path.join(ASSETS_DIR, "images")
    font_path = os.path.join(ASSETS_DIR, "font", "manrope_medium.ttf")

    # Determine image and coordinate file based on type
    if request.tipo == "voucher":
        image_path = os.path.join(image_base_path, "vouch.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_voucher.json")
    elif request.tipo == "detail":
        image_path = os.path.join(image_base_path, "movement_detail.jpg")
        coords_path = os.path.join(COORDS_DIR, "posiciones_textos_detalles.json")
    elif request.tipo == "qr_vouch":
        image_path = os.path.join(image_base_path, "qr", "qr_voucher.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_qr_vouch.json")
    elif request.tipo == "qr_detail":
        image_path = os.path.join(image_base_path, "qr", "qr_detail.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_qr_detail.json")
    else:
        raise HTTPException(status_code=400, detail="Invalid 'tipo' specified. Use 'voucher', 'detail', 'qr_vouch', or 'qr_detail'.")

    # Load image and coordinates
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        with open(coords_path, 'r') as f:
            coords = json.load(f)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Error loading file: {e}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error decoding JSON coordinates file.")

    # Load font
    try:
        font_size = 40  # Cambiado a 14dp como se solicitó
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        raise HTTPException(status_code=500, detail="Error loading font file.")

    # Generar la fecha actual en el formato deseado usando la zona horaria de Colombia
    now = datetime.now(colombia_tz)
    
    # Diccionario de meses en español
    meses = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    
    # Formatear la hora
    hora = now.hour % 12
    if hora == 0:
        hora = 12
    ampm = "a. m." if now.hour < 12 else "p. m."
    
    # Crear la fecha formateada con hora en formato de dos dígitos
    fecha_formateada = f"{now.day} de {meses[now.month]} de {now.year} a las {hora:02d}:{now.minute:02d} {ampm}"
    fecha_formateada = normalizar_texto(fecha_formateada)

    # Crear una copia de los datos para modificar
    datos_modificados = request.datos.dict()
    
    # Establecer "Disponible" 
    datos_modificados["disponible"] = "Disponible"
    
    # Procesar el M-value: si el usuario proporciona un valor, asegurarse de que comience con "M"
    if "mvalue" in datos_modificados and datos_modificados["mvalue"]:
        # Eliminar espacios y caracteres no alfanuméricos
        mvalue = ''.join(filter(str.isalnum, datos_modificados["mvalue"]))
        
        # Si no comienza con "M", agregarla
        if not mvalue.startswith("M"):
            mvalue = "M" + mvalue
            
        datos_modificados["mvalue"] = mvalue
    else:
        # Si no se proporcionó un valor, generar uno aleatorio (comportamiento anterior)
        datos_modificados["mvalue"] = "M" + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    
    # Formatear el número de teléfono con el formato específico: 000 000 0000
    if "phone" in datos_modificados and datos_modificados["phone"]:
        # Eliminar espacios y caracteres no numéricos
        phone = ''.join(filter(str.isdigit, datos_modificados["phone"]))
        
        # Asegurar que tenemos suficientes dígitos (al menos 10)
        if len(phone) >= 10:
            # Formatear como 000 000 0000
            formatted_phone = f"{phone[:3]} {phone[3:6]} {phone[6:10]}"
            
            # Si hay más dígitos, agregar al final
            if len(phone) > 10:
                formatted_phone += " " + phone[10:]
                
            datos_modificados["phone"] = formatted_phone
    
    # Formatear el valor monetario (amount) en formato colombiano: $0.000,00
    if "amount" in datos_modificados and datos_modificados["amount"]:
        try:
            # Eliminar caracteres no numéricos (excepto '.' y ',')
            amount_str = datos_modificados["amount"]
            amount_str = ''.join(c for c in amount_str if c.isdigit() or c in ['.',','])
            
            # Convertir a número, considerando que puede estar en diferentes formatos
            # Si tiene coma decimal, reemplazarla por punto para hacer la conversión
            if ',' in amount_str and '.' not in amount_str:
                amount_num = float(amount_str.replace(',', '.'))
            # Si tiene punto decimal y coma para miles, eliminar comas primero
            elif ',' in amount_str and '.' in amount_str:
                amount_num = float(amount_str.replace(',', ''))
            # En otros casos, intentar convertir directamente
            else:
                amount_num = float(amount_str)
            
            # Formatear con separador de miles (punto) y dos decimales (coma)
            # Primero separamos parte entera y decimal
            int_part = int(amount_num)
            decimal_part = int(round((amount_num - int_part) * 100))
            
            # Formatear parte entera con separadores de miles
            formatted_int = ""
            int_str = str(int_part)
            for i in range(len(int_str)-1, -1, -1):
                formatted_int = int_str[i] + formatted_int
                if (len(int_str)-i) % 3 == 0 and i > 0:
                    formatted_int = "." + formatted_int
            
            # Combinar con los decimales
            formatted_amount = f"$ {formatted_int},{decimal_part:02d}"
            datos_modificados["amount"] = formatted_amount
        except:
            # Si hay algún error, dejar el valor original
            pass
    
    # Normalizar todos los textos antes de escribirlos en la imagen
    for key, value in datos_modificados.items():
        if isinstance(value, str):
            datos_modificados[key] = normalizar_texto(value)
    
    # Write text on the image - usando los datos modificados
    for key, value in datos_modificados.items():
        if key in coords:
            x = coords[key]["x"]
            y = coords[key]["y"]
            draw.text((x, y), str(value), fill=(32, 0, 32), font=font)  # Color #200020 (equivalente a RGB(32, 0, 32))
    
    # Ahora escribimos la fecha generada automáticamente
    if "date" in coords:
        x = coords["date"]["x"]
        y = coords["date"]["y"]
        draw.text((x, y), fecha_formateada, fill=(32, 0, 32), font=font)  # Color #200020

    # Save the image to a bytes buffer and return it
    import io
    buf = io.BytesIO()
    img.save(buf, format='JPEG') # Or PNG, depending on desired output
    byte_im = buf.getvalue()

    return Response(content=byte_im, media_type="image/jpeg") # Or image/png 