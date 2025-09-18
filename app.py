
from flask import Flask, request, jsonify
from bc_recommender import recommend_bc
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/ingest-wgc', methods=['POST'])
def ingest_data():
    data = request.get_json()
    # Here you can store in-memory or process
    return jsonify({"status": "received", "data_points": len(data)}), 200

@app.route('/recommend-bc', methods=['POST'])
def recommend_bc_route():
    data = request.get_json()
    bc = recommend_bc(data)
    return jsonify(bc), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
