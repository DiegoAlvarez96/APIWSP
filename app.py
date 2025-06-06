from flask import Flask, request, jsonify
import requests
import openai
import os
from procesador_rag import construir_indice, buscar_contexto
import sys
from datetime import datetime, timedelta
import json
from openai import OpenAI
from threading import Thread
import pandas as pd
import logging
import difflib

logging.basicConfig(filename="debug.log", level=logging.DEBUG)
app = Flask(__name__)
construir_indice()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = "600271346513044"
NUMEROS_PERMITIDOS = {"5492664745297", "5491122334455", "5493517362123"}
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

USUARIOS_PATH = "usuarios.json"
historial_solicitudes = {}  # clave: telefono, valor: mensaje original que contenia "la solicitud esta correcta"
estado_usuario = {}  # clave: telefono, valor: tipo de flujo ("GENERAL", "SUSCRIPCION", "RESCATE")
estado_usuario2 = {}  # clave: telefono, valor: tipo de flujo ("SUSC", "RESC")

# === UTILIDADES ===
def obtener_tabla_codigos():
    path = "data/INFO FONDOS (FCI).xlsx"
    if os.path.exists(path):
        df = pd.read_excel(path)
        return "\n".join(df.iloc[:, 0].astype(str).tolist())
    return ""

def cargar_usuarios():
    if os.path.exists(USUARIOS_PATH):
        with open(USUARIOS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: datetime.fromisoformat(v) for k, v in data.items()}
    return {}

def guardar_usuarios():
    with open(USUARIOS_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v.isoformat() for k, v in usuarios.items()}, f)

def limpiar_usuarios():
    ahora = datetime.now()
    expirados = [tel for tel, ts in usuarios.items() if ahora - ts > timedelta(hours=8)]
    for tel in expirados:
        usuarios.pop(tel, None)
        estado_usuario.pop(tel, None)
        estado_usuario2.pop(tel, None)
        historial_solicitudes.pop(tel, None)
    guardar_usuarios()

usuarios = cargar_usuarios()
tabla_codigos = obtener_tabla_codigos()

# === WEBHOOK ===
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = "mi_token_de_verificacion"
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == verify_token:
            return request.args.get("hub.challenge"), 200
        return "Token inválido", 403

    if request.method == 'POST':
        data = request.get_json()
        Thread(target=procesar_mensaje, args=(data,)).start()
        return "ok", 200

# === PROCESAR MENSAJE ===
def procesar_mensaje(data):
    try:
        valor = data['entry'][0]['changes'][0]['value']

        if "messages" in valor:
            mensaje = valor['messages'][0]
            telefono = mensaje['from']

            if mensaje.get("type") == "text":
                texto = mensaje['text']['body']
                print(f"📨 Mensaje de {telefono}: {texto}")
                limpiar_usuarios()

                if telefono not in NUMEROS_PERMITIDOS:
                    enviar_respuesta_whatsapp(telefono, "❌ No tiene permisos.")
                    return

                if telefono not in usuarios:
                    print("se comienza mensaje de bienvenida")
                    enviar_bienvenida_con_botones(telefono)
                    usuarios[telefono] = datetime.now()
                    guardar_usuarios()
                    print("mensaje bienvenida exito y guardado usario")
                    return
                
                flujo = estado_usuario.get(telefono)
                #flujo2= estado_usuario2.get(telefono)
                if flujo == "GENERAL":
                    print("se ingresa a general")
                    metadata = responder_con_rag(texto)
                    respuesta = consultar_chatgpt(f"Responder esta consulta: --{texto}-- usando solo esta información:\n{metadata}")
                    enviar_respuesta_con_menu(telefono, respuesta)
                elif flujo == "FCI":
                    enviar_SUSC_RESC_botones()
                elif flujo == "SUSC":
                    
                    print("se ingresa a susc")
                    prompt = (
                        f"Interpretá y tabulá este mensaje:\n{texto}\n"
                        f"para NOMBRE FCI Tenés que buscar el mas parecido en:\n{tabla_codigos}\n"
                        f"Solo devolvé:\nOPERACIÓN: (SUSCRIPCIÓN)\nCOMITENTE: (número)\nNOMBRE FCI: (nombre segun tabla_codigo)\nIMPORTE:  (número en formato pesos $)\n"
                        f"si la info es tabulable y esta completa incluir al final del mensaje (Confirmar si la solicitud está correcta)")
                    respuesta = consultar_chatgpt(prompt)
                    print(respuesta)
                elif flujo == "RESC":
                    print("se ingresa a resc")
                    prompt = (
                        f"Interpretá y tabulá este mensaje:\n{texto}\n"
                        f"para NOMBRE FCI Tenés que buscar el mas parecido en:\n{tabla_codigos}\n"
                        f"Solo devolvé:\nOPERACIÓN: (RESCATE)\nCOMITENTE: (número)\nNOMBRE FCI: (nombre segun tabla_codigo)\nIMPORTE:  (número en formato pesos $) ó CANTIDAD: (número en formato pesos $), completar como importe si en el pensaje incluye $ o pesos si no incluye completar CANTIDAD. \n"
                        f"si la info es tabulable y esta completa incluir al final del mensaje (Confirmar si la solicitud está correcta)")
                    respuesta = consultar_chatgpt(prompt)
                    print(respuesta)
                    
                elif flujo == ANULAR:
                    print("se ingresa a ANULAR")
                    enviar_respuesta_con_menu(telefono, "Por favor pasame el id a anular")
                else:
                    enviar_bienvenida_con_botones(telefono)
                    estado_usuario[telefono] = None

            elif mensaje.get("type") == "interactive" and mensaje["interactive"]["type"] == "button_reply":
                payload = mensaje["interactive"]["button_reply"]["id"]
                print(f"🔘 Botón presionado: {payload}")
            
                if payload == "confirmar_solicitud":
                    texto_original = historial_solicitudes.get(telefono, "")
                    if texto_original:
                        print(texto_original)
                        json_generado = generar_json_para_api(texto_original)
                        enviar_respuesta_con_menu(telefono, f"📦 JSON generado:\n```{json.dumps(json_generado, indent=2)}```")
                    else:
                        enviar_respuesta_con_menu(telefono, "⚠️ No se encontró la solicitud anterior.")
            
                elif payload == "menu_inicial":
                    enviar_bienvenida_con_botones(telefono)
            
                elif payload == "exit":
                    usuarios.pop(telefono, None)
                    estado_usuario.pop(telefono, None)
                    historial_solicitudes.pop(telefono, None)
                    enviar_respuesta_whatsapp(telefono, "🚪 Sesión finalizada. Hasta luego.")
            
                elif payload in ["general", "ANULAR"]:
                    estado_usuario[telefono] = payload.upper()
                    mensaje = "Perfecto. Por favor envíame la consulta."
                    enviar_respuesta_con_menu(telefono, mensaje)
                elif payload == "FCI":
                    enviar_SUSC_RESC_botones()
                elif payload == "SUSC":
                    estado_usuario[telefono] = payload.upper()
                    mensaje = "Perfecto. Por favor envíame los datos para la suscripcion (COMITENT, FONDO Y CLASE, IMPORTE)."
                    enviar_respuesta_con_menu(telefono, mensaje)


        elif "statuses" in valor:
            for estado in valor['statuses']:
                print("🛁 Estado recibido:", estado)

    except Exception as e:
        print("❌ Error en webhook:", e)

# === OPENAI ===
def consultar_chatgpt(texto_usuario):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sos un asistente eficiente y directo."},
            {"role": "user", "content": texto_usuario}
        ]
    )
    return completion.choices[0].message.content

def generar_json_para_api(texto_confirmado):
    prompt = (
        f"A partir de esta solicitud:\n{texto_confirmado}\n\n"
        "Armame el JSON para enviar a la API. Si es SUSCRIPCIÓN:\n"
        'POST /broker/assetManager/mutual_funds/ABREVIATURA/requests/subscription\n'
        'Body:\n{"amount": 100, "bank_account_id": ""}\n\n'
        "Si es RESCATE y se especificó cantidad:\n"
        '{"isTotal": false, "isAmount": false, "shares": 100, "bank_account_id": ""}\n\n'
        "Si es RESCATE y se especificó importe:\n"
        '{"isTotal": false, "isAmount": true, "amount": 100, "bank_account_id": ""}\n\n'
        "Devolveme solo el JSON. Nada más NI UN PUNTO NI LETRA DE MAS."
    )
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    logging.debug(f"json segun chat: {completion.choices[0].message.content}")
    print(completion.choices[0].message.content)  
    try:
        return json.loads(completion.choices[0].message.content)
    except Exception:
        return {"error": "El mensaje no era JSON válido"}

# === WHATSAPP ===
def enviar_respuesta_whatsapp(numero, mensaje):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje}
    }
    r = requests.post(url, headers=headers, json=payload)
    print("Respuesta WhatsApp:", r.status_code, r.text)

def enviar_respuesta_con_menu(numero, mensaje):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": mensaje},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "menu_inicial", "title": "🔙 Menu inicial"}},
                    {"type": "reply", "reply": {"id": "exit", "title": "🚪 Exit"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def enviar_confirmacion_whatsapp(numero, mensaje_original):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": mensaje_original + "\n\n Deseás confirmar esta solicitud"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "confirmar_solicitud", "title": "✅ Confirmar"}},
                    {"type": "reply", "reply": {"id": "menu_inicial", "title": "🔙 Menu inicial"}},
                    {"type": "reply", "reply": {"id": "exit", "title": "🚪 Exit"}}
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=payload)

def enviar_bienvenida_con_botones(numero):
    print("mensaje de bienvenida iniciado")
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "¡Hola! Soy tu asistente virtual 🤖\nSeleccioná una opción para continuar:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "general", "title": "Consultas teso"}},
                    {"type": "reply", "reply": {"id": "FCI", "title": "OPERAR FCI"}},
                    {"type": "reply", "reply": {"id": "ANULAR", "title": "ANULAR SOLICITUD"}}
                ]
            }
        }
    }
    print("se armo el payload")
    response = requests.post(url, headers=headers, json=payload)
    print("mensaje de bienvenida enviado. Status:")
    print(response.status_code)
    print("Respuesta:", response.text)
    logging.debug(f"mensaje de bienvenida enviado. Status: {response.status_code}")
    logging.debug(f"Respuesta: {response.text}")


def enviar_SUSC_RESC_botones(numero):
    print("ENVIO BOTONES SUSSC O RESC")
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Seleccioná una opción para continuar:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "SUSC", "title": "🟢 SUSCRIPCION"}},
                    {"type": "reply", "reply": {"id": "RESC", "title": "🔴 RESCATE"}},
                ]
            }
        }
    }
    print("se armo el payload")
    response = requests.post(url, headers=headers, json=payload)
    print("mensaje de bienvenida enviado. Status:")
    print(response.status_code)
    print("Respuesta:", response.text)
    logging.debug(f"mensaje de bienvenida enviado. Status: {response.status_code}")
    logging.debug(f"Respuesta: {response.text}")
    

# === RAG ===
def responder_con_rag(pregunta_usuario):
    contexto = buscar_contexto(pregunta_usuario)
    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Respondé solo con esta información:\n{contexto}"},
            {"role": "user", "content": pregunta_usuario}
        ]
    )
    return respuesta.choices[0].message.content


def es_similar(texto, frase_objetivo, umbral=0.8):
    print("BUSCANDO SIMILITUD")
    ratio = difflib.SequenceMatcher(None, texto.lower(), frase_objetivo.lower()).ratio()
    print(ratio)
    return ratio >= umbral


# === UTILIDADES EXTRAS ===
@app.route('/usuarios', methods=['GET'])
def ver_usuarios():
    return jsonify({"usuarios": {k: v.isoformat() for k, v in usuarios.items()}})

@app.route('/data/listar', methods=['GET'])
def listar_archivos_data():
    try:
        archivos = os.listdir("data")
        return jsonify({"archivos": archivos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/leer_archivo/<nombre>")
def leer_archivo(nombre):
    ruta = os.path.join("data", nombre)
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read()
    return "Archivo no encontrado", 404

@app.route("/ver_logs")
def ver_logs():
    try:
        with open("debug.log", "r", encoding="utf-8") as f:
            return "<pre>" + f.read() + "</pre>"
    except FileNotFoundError:
        return "⚠️ No hay logs todavía", 404


if __name__ == '__main__':
    app.run(debug=True)
