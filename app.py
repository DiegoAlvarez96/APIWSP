from flask import Flask, request, jsonify
import requests
import openai
import os
from procesador_rag import construir_indice
import sys
from datetime import datetime, timedelta
import json


app = Flask(__name__)
construir_indice()

# Configuraciones
#WHATSAPP_TOKEN = ""
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = "600271346513044"
#OPENAI_API_KEY = ""
NUMEROS_PERMITIDOS = {"5492664745297", "5491122334455"}

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
    "Analizá el siguiente texto y verificá si contiene toda esta información obligatoria:\n"
    "luego te limitaras a responder en base a esto y no estas autorizado a responder otra cosa.\n"
    "el objetivo no es analizar si no cargar una solicitud para eso se solcitia el formato\n"
    "- Número de comitente\n"
    "- Nombre del fondo, deberas buscar en la siguiente listado y encontrar el mas parecido de lo que te pasen\n" 
    f"{tabla_codigos}\n"
    "- Tipo de operación SUSCRIPCION o RESCATE, puede estar abreviado\n"
    "- Importe o cantidad (según el tipo de operación)\n\n"
    "Si falta alguno de estos datos, respondé indicando cuál o cuáles faltan y pedí esa información específicamente.\n"
    "los datos que envio en el ultimo mensaje recuerdalos porque probablemnte se envien solo los faltantes y deberas añadirlos.\n"
    "Si todos los datos están presentes, respondé con el siguiente formato exacto:\n\n"
    "OPERACIÓN: (SUSCRIPCIÓN o RESCATE)\n COMITENTE: (número)\n NOMBRE FCI: (nombre)\n IMPORTE o CANTIDAD: (número)\n\n"
)



openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Verificación del webhook con Meta
        verify_token = "mi_token_de_verificacion"
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == verify_token:
            return request.args.get("hub.challenge"), 200
        return "Token inválido", 403

    if request.method == 'POST':
        data = request.get_json()
    
        try:
            valor = data['entry'][0]['changes'][0]['value']

            
            if "messages" in valor:
                mensaje = valor['messages'][0]
                texto = mensaje['text']['body']
                telefono = mensaje['from']
                limpiar_usuarios()
            
                if telefono in NUMEROS_PERMITIDOS:
                    num = "Autorizado"
                    #enviar_respuesta_whatsapp(telefono, "✅ Bienvenido")
                else:
                    enviar_respuesta_whatsapp(telefono, "❌ No tiene permisos.")
                    sys.exit(1)
                

                
                # Si es el primer mensaje (tipo "text") sin contexto
                if telefono not in usuarios:
                    mensaje_bienvenida = (
                        "¡Hola! Soy tu asistente virtual 🤖\n"
                        "Solo respondo en base a información validada por la empresa.\n"
                        "actualmente solo tabulo informacion de operaciones de FCI. 😊"
                    )
                    enviar_respuesta_whatsapp(telefono, mensaje_bienvenida)
                    usuarios[telefono] = datetime.now()
                    guardar_usuarios()
                    return "ok", 200
                # Usamos RAG
                #respuesta = responder_con_rag(texto)
                
                #directo a apichat gpt
                #estructrua = "en el siguiente texto deberia contener almenos un numero de comitente, un nombre de fondo comun de inversion, una operacion SUSCRIPCION/RESCATE, y un monto o cantidad, en caos de faltar esa informacion por favor respondeme con el dato faltante, en caos de que la informacion este toda respondeme con esa informacion resumida asi: OPERACION: (suscripcion/rescate); COMITENTE:(numero); NOMBRE FCI:(nombre); IMPORTE o CANTIDAD: (NUMERO). EL TEXTO A CONTINUACION: "
                respuesta = consultar_chatgpt(prompt_base + texto)
                # Enviamos respuesta por WhatsApp
                enviar_respuesta_whatsapp(telefono, respuesta)
            else:
                print("📭 No hay mensaje entrante.")
        except Exception as e:
            print("❌ Error en webhook:", e)
    
        return "ok", 200


from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    contexto = buscar_contexto(pregunta_usuario)

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
