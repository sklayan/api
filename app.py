from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# 从环境变量获取 SECRET_KEY，如果没有则报错
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise ValueError("SECRET_KEY 环境变量未设置！请在 Vercel 环境变量中设置。")

app.secret_key = secret_key

# Flask-Login 配置
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面。'

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'amap_app'),
    'user': os.getenv('DB_USER', 'amap_user'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port': os.getenv('DB_PORT', 5432)
}

# 高德API配置
AMAP_WEB_KEY = os.getenv('AMAP_WEB_KEY', '')
AMAP_SERVICE_KEY = os.getenv('AMAP_SERVICE_KEY', '')

# 检查必要环境变量
required_env_vars = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'AMAP_WEB_KEY', 'AMAP_SERVICE_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"缺少必要的环境变量: {', '.join(missing_vars)}")

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, username, email FROM users WHERE id = %s', (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()

    if user_data:
        return User(id=user_data[0], username=user_data[1], email=user_data[2])
    return None

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """初始化数据库表（如果不存在）"""
    conn = get_db_connection()
    cur = conn.cursor()

    # 检查表是否存在，不存在则创建
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()

# 调用初始化数据库
init_db()

# 路由定义
@app.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('map.html', map_key=AMAP_WEB_KEY, username=current_user.username)
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, email, password_hash FROM users WHERE username = %s', (username,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()

        if user_data and check_password_hash(user_data[3], password):
            user = User(id=user_data[0], username=user_data[1], email=user_data[2])
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # 验证输入
        if not username or not email or not password:
            flash('请填写所有字段', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('密码确认不匹配', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('密码长度至少6位', 'error')
            return render_template('register.html')

        # 检查用户是否已存在
        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute('SELECT id FROM users WHERE username = %s OR email = %s', (username, email))
            if cur.fetchone():
                flash('用户名或邮箱已存在', 'error')
                return render_template('register.html')

            # 创建新用户
            password_hash = generate_password_hash(password)
            cur.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id',
                (username, email, password_hash)
            )
            conn.commit()

            flash('注册成功！请登录。', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            flash(f'注册失败: {str(e)}', 'error')
        finally:
            cur.close()
            conn.close()

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录', 'success')
    return redirect(url_for('login'))

# 原有的API路由（添加登录保护）
@app.route('/geocode')
@login_required
def geocode():
    """地理编码：地址转坐标"""
    address = request.args.get('address', '')
    if not address:
        return jsonify({'error': '地址参数缺失'}), 400

    url = 'https://restapi.amap.com/v3/geocode/geo'
    params = {
        'address': address,
        'key': AMAP_SERVICE_KEY,
        'output': 'JSON'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] == '1' and data['geocodes']:
            location = data['geocodes'][0]['location']
            lng, lat = location.split(',')
            return jsonify({
                'success': True,
                'location': {
                    'lng': float(lng),
                    'lat': float(lat)
                },
                'formatted_address': data['geocodes'][0]['formatted_address'],
                'district': data['geocodes'][0].get('district', '')
            })
        else:
            return jsonify({'success': False, 'error': '地址解析失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/reverse_geocode')
@login_required
def reverse_geocode():
    """逆地理编码：坐标转地址"""
    lng = request.args.get('lng', '')
    lat = request.args.get('lat', '')

    if not lng or not lat:
        return jsonify({'error': '坐标参数缺失'}), 400

    url = 'https://restapi.amap.com/v3/geocode/regeo'
    params = {
        'location': f'{lng},{lat}',
        'key': AMAP_SERVICE_KEY,
        'output': 'JSON',
        'extensions': 'base'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] == '1':
            address_component = data['regeocode']['addressComponent']
            formatted_address = data['regeocode']['formatted_address']

            return jsonify({
                'success': True,
                'address': formatted_address,
                'province': address_component.get('province', ''),
                'city': address_component.get('city', ''),
                'district': address_component.get('district', '')
            })
        else:
            return jsonify({'success': False, 'error': '逆地理编码失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/search_poi')
@login_required
def search_poi():
    """搜索周边POI"""
    keywords = request.args.get('keywords', '')
    location = request.args.get('location', '')

    if not keywords or not location:
        return jsonify({'error': '参数缺失'}), 400

    url = 'https://restapi.amap.com/v3/place/around'
    params = {
        'keywords': keywords,
        'location': location,
        'key': AMAP_SERVICE_KEY,
        'output': 'JSON',
        'radius': 5000,
        'offset': 20
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] == '1':
            pois = []
            for poi in data.get('pois', []):
                pois.append({
                    'id': poi['id'],
                    'name': poi['name'],
                    'type': poi['type'],
                    'address': poi['address'],
                    'location': poi['location'],
                    'distance': poi['distance']
                })
            return jsonify({'success': True, 'pois': pois})
        else:
            return jsonify({'success': False, 'error': '搜索失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
