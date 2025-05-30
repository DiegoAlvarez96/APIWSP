from flask import Flask, request, jsonify
import requests
import openai
import os


app = Flask(__name__)

# Configuraciones
WHATSAPP_TOKEN = "EAAKRrfHfOHUBOzq8R5dNBhtzzmVXuwrO5WZCWnaYpoZBTnF0VeneSu7XP8AQyx4Bt0kmBlRzhrqyxZCOyXVZCQFd4jhzpGeKr3NP8YdXvMPZAC6z7OvSvBWmuhoVSvgbVmepbvIAGYD1nd7tMj1VKyEZAeHBrIcXpaZBUXAfQcrZBaP9Mh2hW9qCho32B8gFfR63ycHQ4yLzK9HAfsXtZBZABGw3eUZAoyYup5FM7ZAhEGTqMA6jYW1YxoQZD"
WHATSAPP_PHONE_ID = "600271346513044"
OPENAI_API_KEY = "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"

openai.api_key = OPENAI_API_KEY

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
            mensaje = data['entry'][0]['changes'][0]['value']['messages'][0]
            texto = mensaje['text']['body']
            telefono = mensaje['from']

            # Mandar a ChatGPT
            respuesta = consultar_chatgpt(texto)

            # Responder por WhatsApp
            enviar_respuesta_whatsapp(telefono, respuesta)

        except Exception as e:
            print("Error:", e)

        return "ok", 200

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def consultar_chatgpt(texto_usuario):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Sos un asistente amable y directo."},
            {"role": "user", "content": texto_usuario}
        ]
    )
    return response.choices[0].message.content

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

if __name__ == '__main__':
    app.run(debug=True)
