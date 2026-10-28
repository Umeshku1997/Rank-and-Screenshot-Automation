import os
import sys
import subprocess
import uuid
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
running_processes = {}

@app.route('/')
def home():
    return jsonify({"status": "online", "message": "Automation Cloud Bridge Active"})

@app.route('/run-stream', methods=['GET'])
def run_stream():
    path_param = request.args.get('path', '').strip()
    task_id = request.args.get('task_id', '').strip() or str(uuid.uuid4())

    if not path_param:
        return Response("data: ❌ Error: Path/Repo missing\n\n", mimetype='text/event-stream')

    target_script = ""
    work_dir = BASE_DIR

    # GitHub Repo Pull Support
    if path_param.startswith("github:"):
        try:
            repo_parts = path_param.replace("github:", "").split("#")
            repo_url = repo_parts[0]
            script_name = repo_parts[1] if len(repo_parts) > 1 else "main.py"

            repo_dir_name = f"repo_{uuid.uuid4().hex[:8]}"
            clone_path = os.path.join(BASE_DIR, "downloads", repo_dir_name)

            subprocess.run(["git", "clone", repo_url, clone_path], check=True, capture_output=True)
            work_dir = clone_path
            target_script = os.path.join(clone_path, script_name)
        except Exception as e:
            return Response(f"data: ❌ GitHub Clone Error: {str(e)}\n\n", mimetype='text/event-stream')
    else:
        target_script = path_param if os.path.isabs(path_param) else os.path.normpath(os.path.join(BASE_DIR, path_param))
        work_dir = os.path.dirname(target_script)

    if not os.path.exists(target_script):
        return Response(f"data: ❌ Script File Not Found: {target_script}\n\n", mimetype='text/event-stream')

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["IS_CLOUD"] = "1"

    def generate():
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", target_script],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                bufsize=1
            )
            running_processes[task_id] = process
            yield f"data: [TASK_ID:{task_id}] Cloud Execution Started: {os.path.basename(target_script)}...\n\n"

            for line in iter(process.stdout.readline, ''):
                if line:
                    formatted_line = line.strip().replace("\n", " ")
                    yield f"data: {formatted_line}\n\n"

            process.stdout.close()
            process.wait()
            yield f"data: ✅ Task completed with status code {process.returncode}\n\n"
        except Exception as e:
            yield f"data: ❌ Cloud Execution Error: {str(e)}\n\n"
        finally:
            if task_id in running_processes:
                del running_processes[task_id]

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)