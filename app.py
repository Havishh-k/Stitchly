import os
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from stitching import stitch_images, StitchingError

app = Flask(__name__, static_folder='static', static_url_path='')

# Configuration
UPLOAD_FOLDER = 'temp_uploads'
RESULT_FOLDER = 'temp_results'
app.config['MAX_CONTENT_LENGTH'] = 3 * 10 * 1024 * 1024  # Max 30 MB per request (for 3 images up to 10MB each)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/api/stitch', methods=['POST'])
def api_stitch():
    if 'images[]' not in request.files:
        return jsonify({"status": "error", "error_code": "BAD_REQUEST", "message": "No images provided."}), 400
        
    files = request.files.getlist('images[]')
    
    if len(files) < 2 or len(files) > 3:
        return jsonify({"status": "error", "error_code": "BAD_REQUEST", "message": "Exactly 2 or 3 images required."}), 400
        
    image_bytes_list = []
    
    for file in files:
        if file.filename == '':
            return jsonify({"status": "error", "error_code": "BAD_REQUEST", "message": "One or more files have no filename."}), 400
            
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "error_code": "BAD_REQUEST", "message": f"File type not allowed: {file.filename}"}), 400
            
        # Read file bytes directly
        image_bytes = file.read()
        
        # Check size (10 MB max per file)
        if len(image_bytes) > 10 * 1024 * 1024:
            return jsonify({"status": "error", "error_code": "FILE_TOO_LARGE", "message": f"File {file.filename} exceeds 10MB limit."}), 400
            
        image_bytes_list.append(image_bytes)
        
    try:
        # Get requested format
        output_format = request.form.get('format', 'jpg').lower()
        if output_format not in ['jpg', 'png']:
            output_format = 'jpg'
            
        # Run CV Pipeline
        result_bytes = stitch_images(image_bytes_list, output_format=output_format)
        
        # Save result to disk
        result_filename = f"panorama_{os.urandom(8).hex()}.{output_format}"
        result_path = os.path.join(RESULT_FOLDER, result_filename)
        
        with open(result_path, 'wb') as f:
            f.write(result_bytes)
            
        return jsonify({
            "status": "success",
            "image_url": f"/api/result/{result_filename}"
        })
        
    except StitchingError as e:
        return jsonify({
            "status": "error",
            "error_code": e.code,
            "message": e.message
        }), 422
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({
            "status": "error",
            "error_code": "PROCESSING_ERROR",
            "message": "An unexpected error occurred during processing."
        }), 500

@app.route('/api/result/<filename>')
def serve_result(filename):
    secure_name = secure_filename(filename)
    file_path = os.path.join(RESULT_FOLDER, secure_name)
    if os.path.exists(file_path):
        mimetype = 'image/png' if secure_name.endswith('.png') else 'image/jpeg'
        return send_file(file_path, mimetype=mimetype, as_attachment=False)
    else:
        return jsonify({"status": "error", "message": "Result not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
