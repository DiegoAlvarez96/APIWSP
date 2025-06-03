from flask import Flask, request, jsonify
import requests
import openai
import os
from procesador_rag import construir_indice
import sys

app = Flask(__name__)
construir_indice()

# Configuraciones
#WHATSAPP_TOKEN = ""
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = "600271346513044"
#OPENAI_API_KEY = ""
NUMEROS_PERMITIDOS = {"5492664745297", "5491122334455"}



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

            
                if telefono in NUMEROS_PERMITIDOS:
                    enviar_respuesta_whatsapp(telefono, "✅ Bienvenido")
                else:
                    enviar_respuesta_whatsapp(telefono, "❌ No tiene permisos.")
                    sys.exit(1)

                
                # Si es el primer mensaje (tipo "text") sin contexto
                if mensaje.get("type") == "text" and not mensaje.get("context"):
                    mensaje_bienvenida = (
                        "¡Hola! Soy tu asistente virtual 🤖\n"
                        "Solo respondo en base a información validada por la empresa.\n"
                        "Podés preguntarme sobre políticas, contacto, horarios, etc. 😊"
                    )
                    enviar_respuesta_whatsapp(telefono, mensaje_bienvenida)
    
                # Usamos RAG
                #respuesta = responder_con_rag(texto)
                
                #directo a apichat gpt
                estructrua = "en el siguiente texto deberia contener almenos un numero de comitente, un nombre de fondo comun de inversion, una operacion SUSCRIPCION/RESCATE, y un monto o cantidad, en caos de faltar esa informacion por favor respondeme con el dato faltante, en caos de que la informacion este toda respondeme con esa informacion resumida asi: OPERACION: (suscripcion/rescate); COMITENTE:(numero); NOMBRE FCI:(nombre); IMPORTE o CANTIDAD: (NUMERO). EL TEXTO A CONTINUACION: "
                respuesta = consultar_chatgpt(estructrua + texto)
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

if __name__ == '__main__':
    app.run(debug=True)
