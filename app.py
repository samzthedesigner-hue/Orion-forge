import os
import json
import subprocess
import uuid
import sqlite3
from flask import Flask, request, jsonify, render_template, session
from flask_socketio import SocketIO, emit
import openai
import requests
from groq import Groq
import shutil

app = Flask(__name__)
app.secret_key = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

openai.api_key = OPENAI_API_KEY
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

WORKSPACE_DIR = "/app/workspace"
DB_PATH = "/app/data/jarvis.db"
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs("/app/data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id TEXT PRIMARY KEY, name TEXT, files TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, role TEXT, content TEXT, provider TEXT, model TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

class AIRouter:
    def __init__(self):
        self.providers = [
            {"name": "GROQ", "func": self.ask_groq, "models": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768"]},
            {"name": "DeepSeek", "func": self.ask_deepseek, "models": ["deepseek-chat", "deepseek-coder"]},
            {"name": "OpenRouter", "func": self.ask_openrouter, "models": ["anthropic/claude-3.5-sonnet", "meta-llama/llama-3.1-405b"]},
            {"name": "OpenAI", "func": self.ask_openai, "models": ["gpt-4o-mini", "gpt-4o"]}
        ]
    
    def ask_groq(self, prompt, model="llama-3.1-70b-versatile"):
        if not groq_client: return None
        try:
            res = groq_client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], max_tokens=400
            )
            return res.choices[0].message.content, "GROQ", model
        except: return None
    
    def ask_deepseek(self, prompt, model="deepseek-chat"):
        try:
            r = requests.post("https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 400}, timeout=15
            )
            return r.json()["choices"][0]["message"]["content"], "DeepSeek", model
        except: return None
    
    def ask_openrouter(self, prompt, model="anthropic/claude-3.5-sonnet"):
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 400}, timeout=15
            )
            return r.json()["choices"][0]["message"]["content"], "OpenRouter", model
        except: return None
    
    def ask_openai(self, prompt, model="gpt-4o-mini"):
        try:
            res = openai.ChatCompletion.create(
                model=model, messages=[{"role": "user", "content": prompt}], max_tokens=400
            )
            return res.choices[0].message.content, "OpenAI", model
        except: return None
    
    def ask(self, prompt, project_id=None):
        if project_id:
            save_chat(project_id, "user", prompt, "", "")
        for provider in self.providers:
            result = provider["func"](prompt, provider["models"][0])
            if result:
                reply, provider_name, model = result
                if project_id:
                    save_chat(project_id, "assistant", reply, provider_name, model)
                return reply, provider_name, model
        return "All AI systems offline, Sir.", "Error", "none"

ai_router = AIRouter()

def save_chat(project_id, role, content, provider, model):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (project_id, role, content, provider, model) VALUES (?,?,?,?,?)",
              (project_id, role, content, provider, model))
    conn.commit()
    conn.close()

def get_project_path(project_id):
    path = f"{WORKSPACE_DIR}/{project_id}"
    os.makedirs(path, exist_ok=True)
    return path

def run_code_in_docker(language, project_id, main_file):
    project_dir = get_project_path(project_id)
    if language == "python":
        cmd = f"cd {project_dir} && python {main_file}"
    elif language == "java":
        class_name = main_file.replace(".java", "")
        cmd = f"cd {project_dir} && javac {main_file} && java {class_name}"
    else:
        return "Language not supported", 1
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout + result.stderr, result.returncode
    except Exception as e:
        return str(e), 1

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/projects', methods=['GET', 'POST'])
def projects():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if request.method == 'POST':
        name = request.json['name']
        project_id = str(uuid.uuid4())[:8]
        files = json.dumps({'main.py': 'print("Hello J.A.R.V.I.S")', 'Main.java': 'public class Main{public static void main(String[]a){System.out.println("Hello Java");}}'})
        c.execute("INSERT INTO projects (id, name, files) VALUES (?,?,?)", (project_id, name, files))
        conn.commit()
        get_project_path(project_id)
        conn.close()
        return jsonify({"id": project_id, "name": name})
    else:
        c.execute("SELECT id, name FROM projects ORDER BY created_at DESC")
        projects = [{"id": r[0], "name": r[1]} for r in c.fetchall()]
        conn.close()
        return jsonify(projects)

@app.route('/api/project/<project_id>', methods=['GET', 'POST'])
def project_files(project_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if request.method == 'POST':
        files = request.json['files']
        c.execute("UPDATE projects SET files =? WHERE id =?", (json.dumps(files), project_id))
        conn.commit()
        path = get_project_path(project_id)
        for filename, content in files.items():
            with open(f"{path}/{filename}", "w") as f:
                f.write(content)
        conn.close()
        return jsonify({"status": "saved"})
    else:
        c.execute("SELECT files FROM projects WHERE id =?", (project_id,))
        row = c.fetchone()
        conn.close()
        return jsonify(json.loads(row[0]) if row else {})

@app.route('/api/run', methods=['POST'])
def run_code():
    data = request.json
    output, code = run_code_in_docker(data['language'], data['project_id'], data['main_file'])
    return jsonify({"output": output, "exit_code": code})

@app.route('/api/ask', methods=['POST'])
def ask_ai():
    prompt = request.json['prompt']
    project_id = request.json.get('project_id')
    reply, provider, model = ai_router.ask(prompt, project_id)
    return jsonify({"reply": reply, "provider": provider, "model": model})

@app.route('/api/git', methods=['POST'])
def git_cmd():
    data = request.json
    project_id = data['project_id']
    cmd = data['cmd']
    path = get_project_path(project_id)
    try:
        result = subprocess.run(f"cd {path} && git {cmd}", shell=True, capture_output=True, text=True, timeout=30)
        return jsonify({"output": result.stdout + result.stderr, "success": result.returncode == 0})
    except Exception as e:
        return jsonify({"output": str(e), "success": False})

@app.route('/api/chat/<project_id>')
def get_chat(project_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content, provider, model FROM chat_history WHERE project_id =? ORDER BY created_at ASC", (project_id,))
    chats = [{"role": r[0], "content": r[1], "provider": r[2], "model": r[3]} for r in c.fetchall()]
    conn.close()
    return jsonify(chats)

@socketio.on('terminal_start')
def start_terminal(data):
    project_id = data['project_id']
    emit('terminal_output', {'data': f'J.A.R.V.I.S Terminal - {project_id}\r\n$ '})

@socketio.on('terminal_input')
def terminal_input(data):
    cmd = data['input']
    project_id = data['project_id']
    path = get_project_path(project_id)
    try:
        result = subprocess.run(cmd, shell=True, cwd=path, capture_output=True, text=True, timeout=5)
        emit('terminal_output', {'data': result.stdout + result.stderr + '\r\n$ '})
    except:
        emit('terminal_output', {'data': 'Command timeout\r\n$ '})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)
