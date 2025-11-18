# -*- coding: utf-8 -*-
import os, re, sys, shutil, logging
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from dateutil import parser as dtparser

# ============ CONFIG ============

# Si tu Tesseract no está en PATH, descomenta y ajusta:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CARPETA = "PDFs2"
DESTINO = os.path.join(CARPETA, "Renamed")
os.makedirs(DESTINO, exist_ok=True)

LOGFILE = os.path.join(CARPETA, "renombrador.log")
logging.basicConfig(
    filename=LOGFILE,
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Palabras/fragmentos que NO deben aparecer como nombre
NEGATIVOS = {
    "DATE OF BIRTH","DOB FEMALE","DOB MALE","PATIENT ID","ACCOUNT NO","LOS ANGELES",
    "LOS ","CA ","GLENDALE","DOWNEY","PASADENA","ROSEMEAD","CENTER","HOSPITAL",
    "FAMILY HEALTH","ENDOCRINOLOGY","VISIT","OFFICE","STREET","ST.","BLVD","AVENUE",
    "FAX","COVER","SHEET","RESULT","REPORT","SUMMARY","MRN","ACC NO","ACCNO",
    "BILLING","LAB","LIPID","PANEL","COMPREHENSIVE","METABOLIC","REQUEST","INFORMATION"
}

# ============ UTILIDADES ============

def limpiar_nombre(s: str) -> str:
    # Colapsa espacios y quita caracteres ilegales para archivos
    s = re.sub(r"[\\/*?:\"<>|\r\n]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Evita nombres extremadamente cortos o con números sueltos
    return s

def es_nombre_valido(nombre: str) -> bool:
    up = nombre.upper()
    if len(up) < 5:
        return False
    # Evita palabras negativas
    for neg in NEGATIVOS:
        if neg in up:
            return False
    # Debe tener al menos un espacio (Nombre Apellido)
    if " " not in up:
        return False
    # Evita demasiado número
    if re.search(r"\d{3,}", up):
        return False
    return True

def normalizar_ocr(texto: str) -> str:
    # Arreglos típicos de OCR (solo conservadores)
    rep = {
        "D0B": "DOB",
        "D0 B": "DOB",
        "D.O.B": "DOB",
        "D 0 B": "DOB",
        "0/": "0/",   # deja igual
        " O/": " 0/",
    }
    for a, b in rep.items():
        texto = texto.replace(a, b)
    # Normaliza saltos
    texto = texto.replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto

def normalizar_fecha(fecha_str: str) -> str:
    # Acepta MM/DD/YYYY, M/D/YY, etc. y devuelve MM-DD-YYYY
    fecha_str = fecha_str.strip().replace("\\", "/").replace(".", "/").replace("-", "/")
    # Convierte letras de mes (e.g. Sep 10 2025) si aparecen
    try:
        dt = dtparser.parse(fecha_str, dayfirst=False, fuzzy=True)
        # Corrige años imposibles tipo 1066 que llegan en OCR
        if dt.year < 1900 or dt.year > 2100:
            raise ValueError("Año fuera de rango")
        return dt.strftime("%m-%d-%Y")
    except Exception:
        # Intento directo por regex M/D/YYYY
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", fecha_str)
        if not m:
            raise
        mm, dd, yy = m.groups()
        yy = yy if len(yy) == 4 else ("20" + yy.zfill(2))
        return f"{int(mm):02d}-{int(dd):02d}-{yy}"

def generar_destino(base: str):
    base = limpiar_nombre(base)
    nombre_final = f"{base} - Medical Records.pdf"
    ruta_final = os.path.join(DESTINO, nombre_final)
    i = 1
    while os.path.exists(ruta_final):
        nombre_final = f"{base} ({i}) - Medical Records.pdf"
        ruta_final = os.path.join(DESTINO, nombre_final)
        i += 1
    return ruta_final, nombre_final

def leer_texto_pdf(ruta: str, max_pages=8) -> str:
    texto = []
    try:
        with pdfplumber.open(ruta) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                t = page.extract_text() or ""
                texto.append(t)
    except Exception as e:
        logging.warning(f"pdfplumber falló en {os.path.basename(ruta)}: {e}")
    txt = "\n".join(texto)
    if not txt.strip():
        # OCR primera página
        try:
            imgs = convert_from_path(ruta, dpi=300, first_page=1, last_page=1)
            t = pytesseract.image_to_string(imgs[0])
            txt = t
        except Exception as e:
            logging.error(f"OCR falló en {os.path.basename(ruta)}: {e}")
            txt = ""
    return normalizar_ocr(txt)

# ============ EXTRACCIÓN ============

# Patrones de DOB
DOB_REGEXES = [
    r"\bDOB[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    r"\bDate of Birth[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    r"\bDOB[:\s]*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})",
]

# Patrones de nombre +/- DOB en línea
NAME_DOB_REGEXES = [
    # LAST, FIRST ... DOB: mm/dd/yyyy
    r"\b([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+).*?\bDOB[:\s]*([0-9A-Za-z/,\- ]{4,})",
    # Patient Name: LAST, FIRST ... DOB: ...
    r"\bPatient\s*Name[:\s]*([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+).*?\bDOB[:\s]*([0-9A-Za-z/,\- ]{4,})",
    # Patient: LAST, FIRST ... DOB: ...
    r"\bPatient[:\s]*(?:\d+\s*-\s*)?([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+).*?\bDOB[:\s]*([0-9A-Za-z/,\- ]{4,})",
    # LAST, FIRST ... (edad/sexo) ... fecha después
    r"\b([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)[^ \n]{0,60}?\b(?:DOB|D\.?O\.?B\.?)[:\s]*([0-9A-Za-z/,\- ]{4,})",
]

# Patrones de nombre aislado
NAME_ONLY_REGEXES = [
    r"\bPatient\s*Name[:\s]*([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)\b",
    r"\bPatient[:\s]*(?:\d+\s*-\s*)?([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)\b",
    r"\b([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)\s*(?:DOB|D\.?O\.?B\.?)\b",
]

def formar_nombre(fn: str, ln: str) -> str:
    # Normaliza a "FIRST LAST" en mayúsculas
    nombre = f"{ln} {fn}".strip()  # porque capturamos como (LAST, FIRST)
    nombre = " ".join(w for w in nombre.split() if w)
    nombre = nombre.upper()
    return limpiar_nombre(nombre)

def buscar_por_linea(texto: str):
    """Caso ideal: nombre + DOB en la misma línea/bloque."""
    for rgx in NAME_DOB_REGEXES:
        for m in re.finditer(rgx, texto, flags=re.IGNORECASE|re.DOTALL):
            g1, g2, g3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            try:
                dob = normalizar_fecha(g3)
            except Exception:
                continue
            nombre = formar_nombre(g2, g1)  # (LAST, FIRST) -> FIRST LAST
            if es_nombre_valido(nombre):
                return nombre, dob
    return None, None

def ventana_previa(texto: str, pos: int, ancho=140):
    ini = max(0, pos - ancho)
    return texto[ini:pos]

def buscar_por_proximidad(texto: str):
    """Si encuentro DOB primero, busco LAST, FIRST unos chars antes."""
    for rgx in DOB_REGEXES:
        for m in re.finditer(rgx, texto, flags=re.IGNORECASE):
            raw_fecha = m.group(1)
            try:
                dob = normalizar_fecha(raw_fecha)
            except Exception:
                continue
            win = ventana_previa(texto, m.start(), ancho=200)
            # Busca "LAST, FIRST" inmediatamente antes
            mname = re.search(r"([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)\s*$",
                              win, flags=re.IGNORECASE|re.MULTILINE)
            if not mname:
                # intenta dentro de la ventana (no necesariamente al final)
                mname = re.search(r"([A-Z][A-Za-z' \-]+),\s*([A-Z][A-Za-z' \-]+)",
                                  win, flags=re.IGNORECASE)
            if mname:
                last, first = mname.group(1).strip(), mname.group(2).strip()
                nombre = formar_nombre(first, last)
                if es_nombre_valido(nombre):
                    return nombre, dob
    return None, None

def extraer_nombre_dob(texto: str):
    # 1) Intento directo
    nombre, dob = buscar_por_linea(texto)
    if nombre and dob:
        return nombre, dob
    # 2) Detección por proximidad al DOB
    nombre, dob = buscar_por_proximidad(texto)
    if nombre and dob:
        return nombre, dob
    # 3) Último recurso: nombre solo + DOB en otra línea cercana (misma página)
    #   Tomamos el primer nombre válido que encontremos y la primera DOB global
    first_dob = None
    for rgx in DOB_REGEXES:
        m = re.search(rgx, texto, flags=re.IGNORECASE)
        if m:
            try:
                first_dob = normalizar_fecha(m.group(1))
                break
            except Exception:
                continue
    if first_dob:
        for rgx in NAME_ONLY_REGEXES:
            m = re.search(rgx, texto, flags=re.IGNORECASE)
            if m:
                last, first = m.group(1).strip(), m.group(2).strip()
                nombre = formar_nombre(first, last)
                if es_nombre_valido(nombre):
                    return nombre, first_dob
    return None, None

# ============ MAIN ============

def procesar_pdf(ruta: str):
    texto = leer_texto_pdf(ruta, max_pages=10)
    if not texto.strip():
        return None, None
    nombre, dob = extraer_nombre_dob(texto)
    return nombre, dob

def main():
    no_renombrados = []
    for archivo in os.listdir(CARPETA):
        if not archivo.lower().endswith(".pdf"):
            continue
        ruta = os.path.join(CARPETA, archivo)
        if os.path.isdir(ruta):
            continue
        try:
            nombre, dob = procesar_pdf(ruta)
            if nombre and dob:
                base = f"{nombre} ({dob})"
                dst_path, dst_name = generar_destino(base)
                shutil.move(ruta, dst_path)
                print(f"✔ Renamed: {archivo} ➜ {dst_name}")
                logging.info(f"RENAMED | {archivo} => {dst_name}")
            else:
                print(f"⚠ No se pudo extraer nombre/DOB: {archivo}")
                logging.warning(f"NO_MATCH | {archivo}")
                no_renombrados.append(archivo)
        except Exception as e:
            print(f"❌ Error en {archivo}: {e}")
            logging.exception(f"ERROR | {archivo} | {e}")
            no_renombrados.append(archivo)

    if no_renombrados:
        txt_path = os.path.join(CARPETA, "no_renombrados.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for n in no_renombrados:
                f.write(n + "\n")
        print(f"\nGuardado listado de pendientes en: {txt_path}")
        print(f"Revisa detalles en el log: {LOGFILE}")

if __name__ == "__main__":
    main()