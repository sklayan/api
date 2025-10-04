from app import app
from flask import send_from_directory
import os

# 添加静态文件路由，确保 CSS、JS 等文件可访问
@app.route('/assets/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# Vercel 需要这个变量
handler = app