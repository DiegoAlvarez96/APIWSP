from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = "tutoken123"  # Cambialo por el que pongas en Meta

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Token de verificación inválido", 403

    if request.method == "POST":
        data = request.get_json()
        print("📩 Mensaje recibido:", data)
        return "OK", 200

if __name__ == "__main__":
    app.run()