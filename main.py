from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import json
import os
import datetime
import locale
import random
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

class Data(BaseModel):
    recipient: str
    amount: str
    phone: str
    mvalue: str = ""  # Ahora es opcional, se generará automáticamente
    disponible: str = "Disponible"  # Valor por defecto, se sobreescribirá

class ImageRequest(BaseModel):
    tipo: str
    datos: Data

@app.get("/")
async def read_root():
    return {"message": "API de generación de imágenes Nequi funcionando correctamente"}

@app.post("/generate_image/")
async def generate_image(request: ImageRequest):
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
    else:
        raise HTTPException(status_code=400, detail="Invalid 'tipo' specified. Use 'voucher' or 'detail'.")

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

    # Generar la fecha actual en el formato deseado
    now = datetime.datetime.now()
    # Formato: "dd de (mes) de (yyyy) a las hh:mm a. m. (o p. m.)"
    # Intentamos usar locale para obtener el mes en español
    try:
        fecha_formateada = now.strftime("%-d de %B de %Y a las %I:%M %p")
        # Reemplazar "AM" y "PM" por "a. m." y "p. m."
        fecha_formateada = fecha_formateada.replace("AM", "a. m.").replace("PM", "p. m.")
    except:
        # Si falla, hacemos una implementación manual para los meses
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", 
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        mes = meses[now.month - 1]
        ampm = "a. m." if now.hour < 12 else "p. m."
        hora = now.hour % 12
        if hora == 0:
            hora = 12
        fecha_formateada = f"{now.day} de {mes} de {now.year} a las {hora}:{now.minute:02d} {ampm}"

    # Generar M-value aleatorio (M + 7 dígitos)
    mvalue_aleatorio = "M" + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    
    # Crear una copia de los datos para modificar
    datos_modificados = request.datos.model_dump()
    
    # Siempre establecer "Disponible" y el M-value aleatorio
    datos_modificados["disponible"] = "Disponible"
    datos_modificados["mvalue"] = mvalue_aleatorio
    
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
            formatted_amount = f"${formatted_int},{decimal_part:02d}"
            datos_modificados["amount"] = formatted_amount
        except:
            # Si hay algún error, dejar el valor original
            pass
    
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