from flask import Flask, request, jsonify
from core.parser.pdf_parser import DocumentParser
from core.vector_db.faiss_store import VectorStore
import os

app = Flask(__name__)
parser = DocumentParser()
vector_db = VectorStore()

@app.route('/ingest', methods=['POST'])
def ingest_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
        
    save_path = os.path.join('data/docs', file.filename)
    file.save(save_path)
    
    try:
        chunks = parser.parse_pdf(save_path)
        vector_db.add_documents(chunks)
        return jsonify({
            "status": "success",
            "chunks": len(chunks)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/vector-stats')
def get_vector_stats():
    stats = vector_db.get_vector_stats()
    return jsonify(stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)