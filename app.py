import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # У продакшні пакет може бути відсутній – це нормально
    pass

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

