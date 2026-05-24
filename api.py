from flask import Flask, request, jsonify
from pipeline.main import Pipeline
from runtime.minimal_runtime import MinimalRuntime
import json

app = Flask(__name__)

pipeline = Pipeline()
runtime = MinimalRuntime()

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    prompt = data.get('prompt', '')
    
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    
    output, valid = pipeline.run(prompt)
    
    if valid:
        execution = runtime.execute_schema(output)
        inconsistencies = runtime.validate_endpoints(output)
        execution["inconsistencies"] = inconsistencies
        execution["valid"] = len(inconsistencies) == 0
        output["execution_report"] = execution
    
    return jsonify({
        "output": output,
        "valid": valid,
        "metrics": pipeline.get_metrics()
    })

@app.route('/metrics', methods=['GET'])
def metrics():
    return jsonify(pipeline.get_metrics())

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)