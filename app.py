from flask import Flask, request, jsonify
import requests
import openai
import os
from procesador_rag import construir_indice
import sys
from datetime import datetime, timedelta
import json
from openai import OpenAI
from threading import Thread

app = Flask(__name__)
construir_indice()

# Configuraciones
#WHATSAPP_TOKEN = ""
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = "600271346513044"
#OPENAI_API_KEY = ""
NUMEROS_PERMITIDOS = {"5492664745297", "5491122334455"}
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

USUARIOS_PATH = "usuarios.json"

def obtener_tabla_codigos():
    with open("data/codigos_fci.txt", encoding="utf-8") as f:
        return f.read()
 #memoria de chat iniciados       
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
        del usuarios[tel]
    guardar_usuarios()


usuarios = cargar_usuarios()

tabla_codigos = obtener_tabla_codigos()
prompt_base = (
    "Analizá el siguiente mensaje y verificá si contiene toda esta información obligatoria:\n"
    "luego te limitaras a responder en base a esto y no estas autorizado a responder otra cosa.\n"
    "el objetivo no es analizar si no cargar una solicitud para eso se solcitia el formato\n"
    "- Número de comitente\n"
    "- Nombre del fondo, deberas buscar en la siguiente listado y encontrar el mas parecido de lo que te pasen\n" 
    f"{tabla_codigos}\n"
    "- Tipo de operación SUSCRIPCION o RESCATE, puede estar abreviado o en minuscula en cualquier parte del mensaje, si encuentras esta palabra en el mensaje eso indica la operacion\n"
    "- Importe o cantidad (según el tipo de operación)\n\n"
    "Si falta alguno de estos datos, respondé indicando cuál o cuáles faltan y pedí esa información específicamente.\n"
    "los datos que envio en el ultimo mensaje recuerdalos porque probablemnte se envien solo los faltantes y deberas añadirlos.\n"
    "Si todos los datos están presentes, respondé con el siguiente formato exacto:\n\n"
    "OPERACIÓN: (SUSCRIPCIÓN o RESCATE)\n COMITENTE: (número)\n NOMBRE FCI: (nombre)\n IMPORTE o CANTIDAD: (número), si  el tipo de operacion fue SUSCRIPCION siempre va ser importe, en cambio si es rescate puede ser importe o cantidad\n\n"
)



openai.api_key = os.getenv("OPENAI_API_KEY")

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

def procesar_mensaje(data):      
    try:
        valor = data['entry'][0]['changes'][0]['value']

        if "messages" in valor:
            mensaje = valor['messages'][0]

            if mensaje.get("type") == "text":
                texto = mensaje['text']['body']
                telefono = mensaje['from']
                print(f"📨 Mensaje de {telefono}: {texto}")
                limpiar_usuarios()

                if telefono in NUMEROS_PERMITIDOS:
                    pass  # permitido
                else:
                    enviar_respuesta_whatsapp(telefono, "❌ No tiene permisos.")
                    return "ok", 200

                if telefono not in usuarios:
                    mensaje_bienvenida = (
                        "¡Hola! Soy tu asistente virtual 🤖\n"
                        "Solo respondo en base a información validada por la empresa.\n"
                        "Actualmente solo tabulo información de operaciones de FCI. 😊"
                    )
                    enviar_respuesta_whatsapp(telefono, mensaje_bienvenida)
                    usuarios[telefono] = datetime.now()
                    guardar_usuarios()
                    return "ok", 200
                else:
                    # Si ya es usuario conocido, responder
                    # Usamos RAG
                    print("⏳ Entrando a responder_con_rag...")
                    metadata = responder_con_rag(texto)
                    #print("✅ Respuesta obtenida")
                    #directo con prompt
                    respuesta = consultar_chatgpt(
                        f"Responder este mensaje: --{texto}-- solo basate en la información a continuación, no busques en internet: {metadata} el total de tu respuesta debe tener menos de 4000 caracteres"
                    )
                    enviar_respuesta_whatsapp(telefono, respuesta)

            else:
                print("📎 Evento recibido, pero no es mensaje de texto:", mensaje.get("type"))
                print(f"📨 Mensaje de tipo {tipo} de {telefono}: {mensaje}")
        elif "statuses" in valor:
            estados = valor['statuses']
            for estado in estados:
                print("📡 Estado recibido:", estado)
        else:
            print("📎 Evento recibido sin mensajes ni estados.")

    except Exception as e:
        print("❌ Error en webhook:", e)

    #return "ok", 200







def consultar_chatgpt(texto_usuario):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # O gpt-3.5-turbo o el que quieras
        messages=[
            {"role": "system", "content": "Sos un asistente eficiente y directo."},
            {"role": "user", "content": texto_usuario}
        ]
    )
    return completion.choices[0].message.content

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

from procesador_rag import buscar_contexto

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def responder_con_rag(pregunta_usuario):
    print("🧠 Entrando a buscar_contexto...")
    contexto = buscar_contexto(pregunta_usuario)
    print("✅ Contexto obtenido. Enviando a OpenAI...")

    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Respondé solo con esta información:\n{contexto}"},
            {"role": "user", "content": pregunta_usuario}
        ]
    )
    return respuesta.choices[0].message.content


@app.route('/usuarios', methods=['GET'])
def ver_usuarios():
    return jsonify({
        "usuarios": {k: v.isoformat() for k, v in usuarios.items()}
    })




if __name__ == '__main__':
    app.run(debug=True)
