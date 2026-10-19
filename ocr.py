import os
import re
import shutil
from pathlib import Path
import pytesseract
from PIL import Image

# ==========================================
# 1. INITIAL SETUP
# ==========================================

if shutil.which("tesseract") is None:
    ejecutable_windows = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if ejecutable_windows.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(ejecutable_windows)
        os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"

# Define the folder where we will store the images
CARPETA = Path(__file__).parent / "documentos"

# Valid image extensions to process
EXTENSIONES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

# --psm 6 assumes the image is a single uniform block of text.
# It helps the OCR engine read the document better.
CONFIG_TESSERACT = "--psm 6"


# ==========================================
# 2. IMAGE READING (OCR FUNCTIONS)
# ==========================================

def leer_documento(ruta: Path) -> str:
    """Reads an image using Tesseract and returns the extracted text."""
    imagen = Image.open(ruta)
    
    # Preprocessing: Convert the image to grayscale (black and white).
    # This makes it much easier for the OCR engine to detect letters.
    imagen = imagen.convert("L")

    # Extract text from the image
    return pytesseract.image_to_string(
        imagen,
        lang="spa", # Important: 'spa' tells Tesseract to expect Spanish text (accents, ñ)
        config=CONFIG_TESSERACT,
    )

def cargar_documentos(carpeta: Path = CARPETA) -> dict[str, str]:
    """Reads all images in the folder and returns a dictionary with the text."""
    if not carpeta.exists():
        print(f"WARNING: The folder {carpeta} does not exist.")
        return {}

    documentos = {}
    
    # Loop through all the files inside the folder
    for ruta in sorted(carpeta.iterdir()):
        # Skip files that are not images (like .txt or .pdf files)
        if ruta.suffix.lower() not in EXTENSIONES:
            continue
        try:
            # Read the image and save the text in the dictionary
            documentos[ruta.name] = leer_documento(ruta)
            print(f"  OCR OK: {ruta.name} ({len(documentos[ruta.name])} characters read)")
        except Exception as e:
            print(f"  OCR FAILED in {ruta.name}: {e}")

    return documentos


# ==========================================
# 3. DATA EXTRACTION WITH REGEX
# ==========================================

# Dictionary containing Regular Expressions (Regex) to find specific veterinary data
PATRONES = {
    # Microchip: Usually 15 numeric digits (e.g., 123456789012345)
    "microchip": r"\b\d{15}\b",
    
    # Dates: Formats like 14/03/2026 or 14-3-26
    "fecha": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    
    # Weight: Numbers followed by kg or grams (e.g., 12.5 kg, 3kg, 450 gr)
    "peso": r"\b\d+(?:[.,]\d+)?\s?(?:kg|kilos?|gr|gramos?)\b",
    
    # Medical record or file number (e.g., VET-12345)
    "expediente": r"\b[A-Z]{3}-?\d{5}\b",
}

def normalizar_ocr(texto: str) -> str:
    """
    Fixes common visual mistakes made by the OCR engine before applying Regex.
    For example, Tesseract often confuses the letter 'O' with the number '0'.
    """
    return (
        texto.replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace("S", "5")
        .replace("B", "8")
    )

def extraer_datos(texto: str) -> dict[str, list[str]]:
    """Searches for the regex patterns inside the extracted text."""
    
    # First, clean the text to avoid OCR reading errors
    texto_limpio = normalizar_ocr(texto)
    
    # Use dictionary comprehension to find matches for every pattern
    return {
        campo: re.findall(patron, texto_limpio, re.IGNORECASE)
        for campo, patron in PATRONES.items()
    }


# ==========================================
# 4. MAIN TEST BLOCK
# ==========================================

# This block only runs if you execute this file directly from the terminal
if __name__ == "__main__":
    print("Starting document reading process...")
    documentos = cargar_documentos()

    if not documentos:
        print("\nNo images found. Please put a test photo (.jpg or .png) inside the 'documentos/' folder.")
    
    for nombre, texto in documentos.items():
        print("\n" + "=" * 60)
        print(f"File: {nombre}")
        print("=" * 60)
        print("--- RAW EXTRACTED TEXT ---")
        
        # We print only the first 500 characters to keep the terminal clean
        print(texto[:500]) 
        
        print("\n--- DATA EXTRACTED USING REGEX ---")
        for campo, valores in extraer_datos(texto).items():
            if valores:
                print(f"  {campo}: {valores}")