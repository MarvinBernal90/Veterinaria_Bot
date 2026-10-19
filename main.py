import os
import random
import re
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Import our OCR function 
from ocr import cargar_documentos

# Load environment variables (Gemini API Key)
load_dotenv()

app = FastAPI()

# ==========================================
# 1. MOCK DATABASE
# ==========================================
# Simulate the clinic's client records.
EXPEDIENTES = {
    "VET84729": {
        "titular": "Liliana Guzman",
        "mascota": "Gohan",
        "especie": "Perro",
        "vacunas_al_dia": True,
    },
    "VET11223": {
        "titular": "Marvin Bernal",
        "mascota": "Michi",
        "especie": "Gato",
        "vacunas_al_dia": False,
    },
}

# ==========================================
# 2. DOCUMENT LOADING (RAG)
# ==========================================
print("Cargando documentos con OCR...")
DOCUMENTOS = cargar_documentos()
print(f"Documentos cargados listos para consulta: {len(DOCUMENTOS)}\n")


# ==========================================
# 3. UTILITIES
# ==========================================
def responder(texto: str) -> dict:
    """Returns the exact JSON format that Dialogflow expects to receive."""
    return {"fulfillmentText": texto}

def normalizar_expediente(valor: str) -> str:
    """Cleans the file number format (e.g. 'VET-84729' -> 'VET84729')"""
    return valor.upper().replace(" ", "").replace("-", "").strip()


# ==========================================
# 4. BUSINESS LOGIC
# ==========================================
def gestionar_cita(parametros: dict) -> dict:
    tipo_mascota = parametros.get("tipo_mascota", "")
    telefono = parametros.get("telefono", "")
    
    fecha_cruda = parametros.get("date", "")
    hora_cruda = parametros.get("time", "")

    # CORRECCIÓN: Si Dialogflow envía los datos dentro de una lista, extraemos el primer elemento (texto)
    if isinstance(fecha_cruda, list) and len(fecha_cruda) > 0:
        fecha_cruda = fecha_cruda[0]
        
    if isinstance(hora_cruda, list) and len(hora_cruda) > 0:
        hora_cruda = hora_cruda[0]

    # Format date to DD-MM-YYYY
    fecha_limpia = ""
    if fecha_cruda:
        fecha_iso = fecha_cruda.split("T")[0]
        partes_fecha = fecha_iso.split("-")
        if len(partes_fecha) == 3:
            fecha_limpia = f"{partes_fecha[2]}-{partes_fecha[1]}-{partes_fecha[0]}"
        else:
            fecha_limpia = fecha_iso
            
    # Format time to HH:MM
    hora_limpia = ""
    if hora_cruda:
        if "T" in hora_cruda:
            hora_limpia = hora_cruda.split("T")[1][:5]
        else:
            hora_limpia = hora_cruda[:5]
    
    # Generate a random booking reference for realism
    localizador = f"CITA-{random.randint(1000, 9999)}"
    
    return responder(
        f"Perfecto. He registrado tu solicitud con el localizador {localizador}. "
        f"Tu cita para tu {tipo_mascota} queda pre-reservada para el {fecha_limpia} a las {hora_limpia}. "
        f"Te enviaremos un SMS al {telefono} para confirmar. ¡Gracias!"
    )


# ==========================================
# 5. LANGUAGE MODEL LOGIC (Fallback with Gemini and RAG)
# ==========================================
cliente = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))

INSTRUCCIONES = """Eres el recepcionista virtual de la Clínica Veterinaria Minos. 
Responde de forma muy concisa, amable y directa basándote solo en los documentos. 
No te extiendas demasiado para responder rápido."""

PLANTILLA = """Información de los manuales de la clínica:
{contexto}

Pregunta del cliente: {pregunta}

Por favor, redacta una respuesta amable y completa explicando detalladamente lo que debe hacer el cliente, usando solo la información de arriba."""

def seleccionar_documentos(pregunta: str, n: int = 2) -> str:
    """Finds documents that share keywords with the user's question."""
    if not DOCUMENTOS:
        return ""

    palabras = set(re.findall(r"\w{4,}", pregunta.lower()))
    puntuados = []
    
    for nombre, texto in DOCUMENTOS.items():
        coincidencias = sum(1 for p in palabras if p in texto.lower())
        puntuados.append((coincidencias, nombre, texto))

    puntuados.sort(key=lambda x: x[0], reverse=True)
    elegidos = [t for c, _, t in puntuados[:n] if c > 0]

    return "\n\n---\n\n".join(elegidos)

def preguntar_al_modelo(prompt: str) -> str:
    """Sends the context and question to Gemini using the standard generate_content."""
    respuesta = cliente.models.generate_content(
        model="gemini-3.1-flash-lite",  
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES,
            temperature=0.2,
            max_output_tokens=250,
        ),
    )
    return respuesta.text.strip()

def gestionar_fallback(pregunta: str) -> dict:
    contexto = seleccionar_documentos(pregunta)

    if not contexto:
        return responder(
            "No tengo documentación a mano sobre ese tema específico. ¿Quieres que te pase con un veterinario?"
        )

    prompt = PLANTILLA.format(contexto=contexto, pregunta=pregunta)

    try:
        respuesta_llm = preguntar_al_modelo(prompt)
        
        print("\n--- TEXTO EXTRAÍDO POR OCR (CONTEXTO) ---")
        print(contexto)
        print("--- RESPUESTA DE GEMINI ---")
        print(respuesta_llm)
        print("-" * 50)
        
        return responder(respuesta_llm)
    except Exception as e:
        print("ERROR LLM:", e)
        return responder(
            "En este momento tengo problemas técnicos para consultar los manuales. ¿Te paso con recepción?"
        )


# ==========================================
# 6. MAIN ENDPOINT (Receives Dialogflow requests)
# ==========================================
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    resultado = body["queryResult"]
    intencion = resultado["intent"]["displayName"]
    parametros = resultado.get("parameters", {})
    pregunta = resultado.get("queryText", "")

    print("-" * 50)
    print("INTENCIÓN:", intencion)
    print("PARÁMETROS:", parametros)
    print("TEXTO:", pregunta)

    # If the intent is to schedule an appointment 
    if intencion == "agendar_cita - confirmacion_si" or intencion == "agendar_cita":
        # Make sure Dialogflow has already collected all the required data
        if not resultado.get("allRequiredParamsPresent", False):
            return {} 
        return gestionar_cita(parametros)

    # If the intent is a question the bot doesn't know (Fallback)
    if intencion == "Default Fallback Intent":
        return gestionar_fallback(pregunta)

    return responder("Todavía no sé gestionar esa petición específica.")

@app.get("/")
def raiz():
    """Health check to see if the server is alive."""
    return {"estado": "ok", "documentos_cargados": len(DOCUMENTOS)}