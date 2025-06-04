import os
import fitz  # PyMuPDF
import pandas as pd
#import chromadb
#from chromadb.utils import embedding_functions
#from chromadb import PersistentClient

#os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Crear cliente Chroma y colección
#chroma_client = chromadb.Client()
#chroma_client = PersistentClient(path="/data/chroma_db")
#collection = chroma_client.get_or_create_collection("base_conocimiento")


# Función para extraer texto de PDF
def leer_pdf(path):
    doc = fitz.open(path)
    texto = "\n".join([page.get_text() for page in doc])
    return texto

# Función para extraer texto de Excel
def leer_excel(path):
    df = pd.read_excel(path)
    return "\n".join(df.astype(str).apply(lambda row: " | ".join(row), axis=1))

# Función para extraer texto de TXT
def leer_txt(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

# Carga todos los archivos de /data
def cargar_documentos():
    documentos = []
    ruta_data = "data"

    for archivo in os.listdir(ruta_data):
        path = os.path.join(ruta_data, archivo)
        if archivo.endswith(".pdf"):
            documentos.append(leer_pdf(path))
        elif archivo.endswith(".txt"):
            documentos.append(leer_txt(path))
        elif archivo.endswith(".xlsx") or archivo.endswith(".xls"):
            documentos.append(leer_excel(path))
    print ("se cargaron los docs")
    
    return documentos

# Fragmentar texto en chunks
def fragmentar(texto, tamaño=800):
    partes = texto.split("\n")
    chunks = []
    actual = ""
    for linea in partes:
        if len(actual) + len(linea) < tamaño:
            actual += linea + " "
        else:
            chunks.append(actual.strip())
            actual = linea + " "
    if actual:
        chunks.append(actual.strip())
    return chunks

# Indexar los textos en ChromaDB
def construir_indice():
    documentos = cargar_documentos()
    global CONTEXTO_MEMORIA
    CONTEXTO_MEMORIA = "\n---\n".join(fragmentar("\n".join(documentos)))
    print(f"📚 Contexto cargado en memoria. Fragmentos: {len(CONTEXTO_MEMORIA.split('---'))}")
    
# Buscar el fragmento más relevante


def buscar_contexto(pregunta):
    print("🔍 Buscando memoria...", pregunta)
    return CONTEXTO_MEMORIA
