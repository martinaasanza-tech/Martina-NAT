import os, re, shutil
import pandas as pd
from PyPDF2 import PdfReader

# === CONFIG ===
BASE = r"C:\Users\RYZEN 5\Desktop\NAT\AUTHS OCR"
INPUT_DIR = os.path.join(BASE, "input_pdf")
PROCESSED_DIR = os.path.join(BASE, "processed")
OUTPUT_XLSX = os.path.join(BASE, "outputs", "autorizaciones.xlsx")
FORBIDDEN = r'<>:"/\\|?*'

# === FUNCIONES ===
def ensure_dirs():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_XLSX), exist_ok=True)

def read_pdf_text(path):
    text = []
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            text.append(page.extract_text() or "")
    except Exception as e:
        print(f"[ERROR] No se pudo leer {path}: {e}")
    return "\n".join(text)

def clean_text(txt):
    return " ".join(txt.split())

def title_case(s):
    return " ".join(w.capitalize() for w in s.lower().split())

def clean_filename(s):
    s = " ".join((s or "").split())
    for ch in FORBIDDEN:
        s = s.replace(ch, "")
    return s.strip()[:150]

# === EXTRACTORES ===
def extract_patient_name(text):
    text = text.replace("MEMS NAME", "MEMB NAME").replace("MEMN NAME", "MEMB NAME")
    m = re.search(r"MEMB\s*NAME[:\s]*([A-ZÁÉÍÓÚÑ ,.'\-]+)", text, re.I)
    if not m:
        return ""
    raw = m.group(1)
    name = " ".join(reversed([p.strip() for p in raw.split(",") if p.strip()]))  # invierte apellido,nombre
    name = re.sub(r"\b([A-Z])\b", "", name)  # elimina iniciales sueltas
    name = re.sub(r"\s{2,}", " ", name)
    return title_case(name.strip())

def extract_dob(text):
    m = re.search(r"DATE\s*OF\s*BIRTH[:\s]*([0-9OQIlSsCBZ]{6,12})", text, re.I)
    if not m:
        return ""
    dob = m.group(1)
    dob = dob.translate(str.maketrans("OQIlSsCBZ", "001155682")).replace("-", "/")
    dob = re.sub(r"(\d{2})(\d{2})(\d{4})", r"\1/\2/\3", dob)
    dob = re.sub(r"(\d{1,2})[^\d](\d{1,2})[^\d](\d{2,4})", r"\1/\2/\3", dob)
    if len(dob) == 8 and "/" not in dob:
        dob = dob[:2] + "/" + dob[2:4] + "/" + dob[4:]
    return dob

def extract_pcp(text):
    m = re.search(r"REFERRING\s+PHYSICIAN.*?NAME[:\s]*([A-ZÁÉÍÓÚÑ ,.'\-]+)", text, re.I | re.S)
    if not m:
        m = re.search(r"PRIMARY\s+CARE\s+PHYSICIAN.*?NAME[:\s]*([A-ZÁÉÍÓÚÑ ,.'\-]+)", text, re.I | re.S)
    if not m:
        return ""
    raw = m.group(1)
    raw = raw.replace("NAME", "").replace(":", "").strip()
    raw = re.sub(r"\s{2,}", " ", raw)
    return title_case(raw)

def extract_ipa(text):
    m = re.search(r"^\s*([A-Z0-9 ,.'&/\-]+IPA)\s*$", text, re.I | re.M)
    if not m:
        m = re.search(r"([A-Z][A-Z0-9 ,.'&/\-]*MEDICAL\s+GROUP[^\n]*)", text, re.I)
    ipa = m.group(1).strip() if m else ""
    ipa = re.sub(r"\s{2,}", " ", ipa)
    return title_case(ipa)

# === PROCESAMIENTO ===
def rename_file(original_path, patient_name):
    if not patient_name:
        patient_name = os.path.splitext(os.path.basename(original_path))[0]
    new_name = clean_filename(patient_name) + ".pdf"
    dst = os.path.join(PROCESSED_DIR, new_name)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        i = 2
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        dst = f"{base} ({i}){ext}"
    shutil.move(original_path, dst)
    return dst

def process_all():
    ensure_dirs()
    data = []
    pdfs = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]

    if not pdfs:
        print("⚠️ No hay PDFs en la carpeta input_pdf.")
        return

    for pdf in pdfs:
        path = os.path.join(INPUT_DIR, pdf)
        print(f"Procesando: {pdf}")
        text = read_pdf_text(path)
        name = extract_patient_name(text)
        dob = extract_dob(text)
        pcp = extract_pcp(text)
        ipa = extract_ipa(text)

        data.append({
            "Patient Name": name,
            "DOB": dob,
            "PCP": pcp,
            "IPA": ipa
        })
        renamed = rename_file(path, name)
        print(f"  → {os.path.basename(renamed)}")

    df = pd.DataFrame(data, columns=["Patient Name", "DOB", "PCP", "IPA"])
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"\n✅ Archivo Excel generado en:\n{OUTPUT_XLSX}")

if __name__ == "__main__":
    process_all()
