from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "tutoken123"  # Este debe coincidir con lo que pusiste en Meta

@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        mode = request.args.get("hub.mode")

        if token == VERIFY_TOKEN and mode == "subscribe":
            return str(challenge), 200, {"Content-Type": "text/plain"}
        else:
            return "Token inválido", 403

    if request.method == "POST":
        data = request.get_json()
        print("📥 Webhook recibido:", json.dumps(data, indent=2))

        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value")
                    messages = value.get("messages")
                    if messages:
                        for msg in messages:
                            numero = msg["from"]
                            texto = msg.get("text", {}).get("body", "")
                            print(f"📨 Mensaje de {numero}: {texto}")
                            # Podés guardar esto, responder, disparar acciones, etc.

        return "OK", 200
