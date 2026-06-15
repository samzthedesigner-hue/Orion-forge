import os
import subprocess
import sys
from flask import Flask, render_template, request, jsonify, session
from groq import Groq
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'jarvis-dev-key-change-in-prod')

# API Clients
groq_client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run_code():
    data = request.get_json()
    code = data.get('code', '')
    language = data.get('language', 'python')
    
    try:
        if language == 'python':
            # Run Python code
            result = subprocess.run(
                [sys.executable, '-c', code],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout
            error = result.stderr
        else:
            output = "Only Python execution supported in this version"
            error = ""
            
        return jsonify({
            'output': output,
            'error': error,
            'success': result.returncode == 0 if language == 'python' else True
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({
            'output': '',
            'error': 'Code execution timed out after 10 seconds',
            'success': False
        })
    except Exception as e:
        return jsonify({
            'output': '',
            'error': str(e),
            'success': False
        })

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '')
    model = data.get('model', 'groq')
    
    try:
        if model == 'groq':
            response = groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": user_message}],
                temperature=0.7,
                max_tokens=1024
            )
            reply = response.choices[0].message.content
        else:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": user_message}],
                temperature=0.7,
                max_tokens=1024
            )
            reply = response.choices[0].message.content
            
        return jsonify({
            'reply': reply,
            'success': True
        })
    
    except Exception as e:
        return jsonify({
            'reply': f'Error: {str(e)}',
            'success': False
        })

@app.route('/files', methods=['GET', 'POST'])
def handle_files():
    if request.method == 'GET':
        # List files in workspace
        try:
            files = []
            for filename in os.listdir('/app/workspace'):
                if os.path.isfile(os.path.join('/app/workspace', filename)):
                    files.append(filename)
            return jsonify({'files': files})
        except:
            return jsonify({'files': []})
    
    elif request.method == 'POST':
        # Save file
        data = request.get_json()
        filename = data.get('filename', 'untitled.py')
        content = data.get('content', '')
        
        try:
            os.makedirs('/app/workspace', exist_ok=True)
            with open(f'/app/workspace/{filename}', 'w') as f:
                f.write(content)
            return jsonify({'success': True, 'message': f'Saved {filename}'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

@app.route('/load/<filename>', methods=['GET'])
def load_file(filename):
    try:
        with open(f'/app/workspace/{filename}', 'r') as f:
            content = f.read()
        return jsonify({'content': content, 'success': True})
    except Exception as e:
        return jsonify({'content': '', 'success': False, 'error': str(e)})

if __name__ == '__main__':
    os.makedirs('/app/workspace', exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=True)
