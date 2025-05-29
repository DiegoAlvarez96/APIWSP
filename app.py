from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "tutoken123"  # Este debe coincidir con lo que pusiste en Meta

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        # Verificación de Meta
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        mode = request.args.get("hub.mode")

        if token == VERIFY_TOKEN and mode == "subscribe":
            return str(challenge), 200, {"Content-Type": "text/plain"}
        else:
            return "Token inválido", 403

    if request.method == "POST":
        data = request.get_json()
        print("📩 Mensaje recibido:", data)
        return "OK", 200
