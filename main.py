from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar credenciales de Firebase desde variables de entorno
firebase_config = {
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
}

# Inicializar Firebase con las credenciales
cred = credentials.Certificate(firebase_config)
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

# Firma SHA256 esperada para validación
EXPECTED_APP_SIGNATURE = "3fa5cac437fbd181be09106f87d5f0e8a693f44112732abf988d8f0ee0ff0170"

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

# Diccionario para almacenar las peticiones por token
token_request_counts = defaultdict(lambda: {"count": 0, "reset_time": datetime.now() + timedelta(minutes=1)})

# Función para verificar el rate limit por token
def check_token_rate_limit(token: str) -> bool:
    current_time = datetime.now()
    
    # Si el tiempo de reset ha pasado, reiniciar el contador
    if current_time > token_request_counts[token]["reset_time"]:
        token_request_counts[token] = {"count": 0, "reset_time": current_time + timedelta(minutes=1)}
    
    # Incrementar el contador
    token_request_counts[token]["count"] += 1
    
    # Verificar si se excedió el límite (5 peticiones por minuto)
    return token_request_counts[token]["count"] <= 5

# Función para verificar el token de Firebase
async def verify_firebase_token(request: Request) -> str:
    # Obtener el token del header Authorization
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="NULL"
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
    app_signature: str = ""  # Firma SHA256 de la aplicación
    banco: str = ""  # Campo para los tipos bc_vouch y bc_detail
    numero_cuenta: str = ""  # Campo para los tipos bc_vouch y bc_detail

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
        <title>Nequi Alpha</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700&display=swap');
            
            body {{
                font-family: 'Orbitron', sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background-color: #0F1C2E;
                color: #7DF9FF;
                text-align: center;
                background-image: 
                    radial-gradient(circle at 20% 30%, #1a4875 0%, transparent 20%),
                    radial-gradient(circle at 80% 70%, #1a4875 0%, transparent 20%);
                overflow: hidden;
                position: relative;
            }}
            
            body::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(45deg, transparent 49%, #00f2ff 49%, #00f2ff 51%, transparent 51%);
                background-size: 6px 6px;
                opacity: 0.1;
                z-index: -1;
            }}
            
            .container {{
                max-width: 800px;
                padding: 40px;
                background-color: rgba(16, 24, 39, 0.8);
                border: 1px solid #00f2ff;
                border-radius: 20px;
                box-shadow: 0 0 20px rgba(0, 242, 255, 0.3), 
                            0 0 40px rgba(0, 242, 255, 0.1) inset;
                backdrop-filter: blur(5px);
                position: relative;
                z-index: 1;
                animation: pulse 4s infinite alternate;
            }}
            
            @keyframes pulse {{
                0% {{ box-shadow: 0 0 20px rgba(0, 242, 255, 0.3), 0 0 40px rgba(0, 242, 255, 0.1) inset; }}
                100% {{ box-shadow: 0 0 30px rgba(0, 242, 255, 0.5), 0 0 60px rgba(0, 242, 255, 0.2) inset; }}
            }}
            
            h1 {{
                font-size: 2.5em;
                margin-bottom: 30px;
                text-transform: uppercase;
                letter-spacing: 3px;
                color: #fff;
                text-shadow: 0 0 10px #00f2ff, 0 0 20px #00f2ff;
            }}
            
            p {{
                font-size: 1.2em;
                line-height: 1.8;
                margin-bottom: 25px;
                color: #a4cdde;
            }}
            
            .status {{
                display: inline-block;
                padding: 12px 24px;
                background-color: rgba(0, 242, 255, 0.2);
                border: 1px solid #00f2ff;
                border-radius: 30px;
                font-weight: bold;
                margin-top: 30px;
                position: relative;
                overflow: hidden;
            }}
            
            .status::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
                animation: shine 3s infinite;
            }}
            
            @keyframes shine {{
                to {{ left: 100%; }}
            }}
            
            .time {{
                margin-top: 25px;
                font-size: 1.1em;
                color: #00f2ff;
                letter-spacing: 1px;
                text-shadow: 0 0 5px rgba(0, 242, 255, 0.5);
            }}
            
            .dots {{
                position: absolute;
                width: 100%;
                height: 100%;
                top: 0;
                left: 0;
                pointer-events: none;
                z-index: -1;
            }}
            
            .dot {{
                position: absolute;
                width: 2px;
                height: 2px;
                background-color: rgba(0, 242, 255, 0.5);
                border-radius: 50%;
                animation: float 3s infinite alternate;
            }}
            
            @keyframes float {{
                from {{ transform: translateY(0) rotate(0deg); }}
                to {{ transform: translateY(-20px) rotate(360deg); }}
            }}
            
            .hexagon {{
                position: absolute;
                width: 100px;
                height: 60px;
                background-color: rgba(0, 242, 255, 0.05);
                border: 1px solid rgba(0, 242, 255, 0.1);
                clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);
                z-index: -1;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>NEQUI ALPHA</h1>
            <p>Bienvenido al sistema de generación de imágenes de nueva generación. Esta API utiliza algoritmos de inteligencia artificial avanzados para procesar y generar elementos visuales con precisión cuántica.</p>
            <p>Para acceder al sistema, envía solicitudes POST autenticadas al endpoint /generate_image/ con los parámetros de configuración requeridos.</p>
            <div class="status">ESTADO: OPERATIVO</div>
            <div class="time">TIEMPO ACTUAL: {current_time}</div>
        </div>
        
        <script>
            // Crear puntos flotantes y hexágonos para el efecto futurista
            document.addEventListener('DOMContentLoaded', function() {{
                const body = document.querySelector('body');
                
                // Crear puntos
                for (let i = 0; i < 50; i++) {{
                    const dot = document.createElement('div');
                    dot.classList.add('dot');
                    dot.style.left = Math.random() * 100 + '%';
                    dot.style.top = Math.random() * 100 + '%';
                    dot.style.animationDuration = (Math.random() * 3 + 2) + 's';
                    dot.style.animationDelay = (Math.random() * 2) + 's';
                    body.appendChild(dot);
                }}
                
                // Crear hexágonos
                for (let i = 0; i < 10; i++) {{
                    const hexagon = document.createElement('div');
                    hexagon.classList.add('hexagon');
                    hexagon.style.left = Math.random() * 100 + '%';
                    hexagon.style.top = Math.random() * 100 + '%';
                    hexagon.style.transform = 'rotate(' + (Math.random() * 360) + 'deg)';
                    hexagon.style.opacity = Math.random() * 0.5;
                    body.appendChild(hexagon);
                }}
            }});
        </script>
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
    # Verificar autenticación y obtener token
    token = await verify_firebase_token(request_obj)
    
    # Verificar rate limit por token
    if not check_token_rate_limit(token):
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor: No se pudo procesar la solicitud en este momento. Por favor, intente más tarde."
        )
    
    # Base paths con rutas relativas desde el directorio base
    image_base_path = os.path.join(ASSETS_DIR, "images")

    # Determine image and coordinate file based on type
    if request.tipo == "voucher":
        image_path = os.path.join(image_base_path, "vouch.png")
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
    elif request.tipo == "transfiya":
        image_path = os.path.join(image_base_path, "transfiya.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_transfiya.json")
    elif request.tipo == "bc_vouch":
        image_path = os.path.join(image_base_path, "bc", "plantilla_bc_vouch.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_bc_vouch.json")
    elif request.tipo == "bc_detail":
        image_path = os.path.join(image_base_path, "bc", "plantilla_bc_detail.jpg")
        coords_path = os.path.join(COORDS_DIR, "pociciones_textos_bc_detail.json")
    else:
        raise HTTPException(status_code=400, detail="Invalid 'tipo' specified. Use 'voucher', 'detail', 'qr_vouch', 'qr_detail', 'transfiya', 'bc_vouch', or 'bc_detail'.")

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
        # Determinar qué fuente usar según el tipo
        if request.tipo in ["qr_vouch", "qr_detail", "transfiya"]:
            font_path = os.path.join(ASSETS_DIR, "font", "manrope_regular.ttf")
            font_size = 42  # Tamaño más grande para QR y transfiya
        else:
            font_path = os.path.join(ASSETS_DIR, "font", "manrope_medium.ttf")
            font_size = 40  # Tamaño normal para otros tipos
            
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
    
    # Formatear la fecha según el tipo de comprobante
    if request.tipo == "bc_vouch" or request.tipo == "bc_detail":
        # Formato especial para bc_vouch y bc_detail: "0 de (mes) de (AAAA), X:XX P/A. M."
        hora = now.hour % 12
        if hora == 0:
            hora = 12
        ampm = "A. M." if now.hour < 12 else "P. M."
        
        # Día sin cero a la izquierda
        dia_formateado = f"{now.day}"
        
        # Formato especial para bc_vouch y bc_detail
        fecha_formateada = f"{dia_formateado} de {meses[now.month]} de {now.year}, {hora}:{now.minute:02d} {ampm}"
    else:
        # Formato estándar para otros tipos
        hora = now.hour % 12
        if hora == 0:
            hora = 12
        ampm = "a. m." if now.hour < 12 else "p. m."
        
        # Formatear el día con cero a la izquierda si es menor que 10
        dia_formateado = f"{now.day:02d}"  # Esto asegura que siempre tenga 2 dígitos
        
        # Crear la fecha formateada con el día con cero a la izquierda
        fecha_formateada = f"{dia_formateado} de {meses[now.month]} de {now.year} a las {hora:02d}:{now.minute:02d} {ampm}"

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
        # Si no se proporcionó un valor, generar uno aleatorio con 8 dígitos (entre 10000000 y 99999999)
        random_number = random.randint(10000000, 99999999)
        datos_modificados["mvalue"] = "M" + str(random_number)
    
    # Formatear el número de teléfono con el formato específico: 000 000 0000
    if "phone" in datos_modificados and datos_modificados["phone"]:
        # Eliminar espacios y caracteres no numéricos
        phone = ''.join(filter(str.isdigit, datos_modificados["phone"]))
        
        # Para tipo transfiya, dejar el número sin espacios
        if request.tipo == "transfiya":
            datos_modificados["phone"] = phone
        else:
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
    
    # Para comprobantes de tipo bc_vouch o bc_detail, establecer el banco como Bancolombia
    if request.tipo == "bc_vouch" or request.tipo == "bc_detail":
        datos_modificados["banco"] = "Bancolombia"
    
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

    # Asegurar que la imagen esté en modo RGB con toda la profundidad de color
    img = img.convert('RGB')

    # Save the image to a bytes buffer and return it with máxima calidad posible
    import io
    buf = io.BytesIO()
    
    # Guardar la imagen con la máxima calidad posible
    # format='PNG' - PNG sin pérdida para máxima calidad
    # compress_level=0 - Sin compresión (máxima calidad)
    # optimize=False - Sin optimizaciones que puedan reducir calidad
    img.save(buf, format='PNG', compress_level=0, optimize=True)
    
    byte_im = buf.getvalue()

    # Devolver con el tipo MIME correspondiente para PNG
    media_type = "image/png"
    return Response(content=byte_im, media_type=media_type) 