from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
import psycopg2
from dotenv import load_dotenv

# 只在本地加载环境变量
if os.path.exists('.env.local'):
    load_dotenv('.env.local')

app = Flask(__name__)

# 从环境变量获取配置
secret_key = os.getenv('SECRET_KEY', 'vercel-default-secret-key-change-in-production')
app.secret_key = secret_key

# Flask-Login 配置
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面。'

# 数据库配置 - 使用Vercel环境变量
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST'),
    'database': os.getenv('POSTGRES_DATABASE'),
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD'),
    'port': int(os.getenv('POSTGRES_PORT', 5432))
}

# 高德API配置
AMAP_WEB_KEY = os.getenv('AMAP_WEB_KEY')
AMAP_SERVICE_KEY = os.getenv('AMAP_SERVICE_KEY')

# 检查必要环境变量
def check_environment():
    missing_configs = []
    if not AMAP_WEB_KEY:
        missing_configs.append('AMAP_WEB_KEY')
    if not AMAP_SERVICE_KEY:
        missing_configs.append('AMAP_SERVICE_KEY')
    if not all([DB_CONFIG['host'], DB_CONFIG['database'], DB_CONFIG['user'], DB_CONFIG['password']]):
        missing_configs.append('数据库配置')
    
    if missing_configs:
        print("⚠️  警告: 以下配置缺失:", ", ".join(missing_configs))
        return False
    return True

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None
        cur = conn.cursor()
        cur.execute('SELECT id, username, email FROM users WHERE id = %s', (user_id,))
        user_data = cur.fetchone()
        if user_data:
            return User(id=user_data[0], username=user_data[1], email=user_data[2])
        return None
    except Exception as e:
        print(f"加载用户失败: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return None

def init_db():
    """初始化数据库表"""
    conn = get_db_connection()
    if conn is None:
        print("❌ 无法连接到数据库，跳过初始化")
        return
        
    cur = None
    try:
        cur = conn.cursor()
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
        print("✅ 数据库初始化成功")
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# 初始化数据库
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
        if conn is None:
            flash('数据库连接失败', 'error')
            return render_template('login.html')

        cur = None
        try:
            cur = conn.cursor()
            cur.execute('SELECT id, username, email, password_hash FROM users WHERE username = %s', (username,))
            user_data = cur.fetchone()

            if user_data and check_password_hash(user_data[3], password):
                user = User(id=user_data[0], username=user_data[1], email=user_data[2])
                login_user(user)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash('用户名或密码错误', 'error')

        except Exception as e:
            flash(f'登录失败: {str(e)}', 'error')
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

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

        conn = get_db_connection()
        if conn is None:
            flash('数据库连接失败', 'error')
            return render_template('register.html')

        cur = None
        try:
            cur = conn.cursor()

            # 检查用户是否已存在
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
            if conn:
                conn.rollback()
            flash(f'注册失败: {str(e)}', 'error')
            return render_template('register.html')
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录', 'success')
    return redirect(url_for('login'))

@app.route('/geocode')
@login_required
def geocode():
    """地理编码：地址转坐标"""
    address = request.args.get('address', '')
    if not address:
        return jsonify({'error': '地址参数缺失'}), 400

    if not AMAP_SERVICE_KEY:
        return jsonify({'success': False, 'error': '高德API配置缺失'})

    url = 'https://restapi.amap.com/v3/geocode/geo'
    params = {
        'address': address,
        'key': AMAP_SERVICE_KEY,
        'output': 'JSON'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
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
            return jsonify({'success': False, 'error': data.get('info', '地址解析失败')})
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

    if not AMAP_SERVICE_KEY:
        return jsonify({'success': False, 'error': '高德API配置缺失'})

    url = 'https://restapi.amap.com/v3/geocode/regeo'
    params = {
        'location': f'{lng},{lat}',
        'key': AMAP_SERVICE_KEY,
        'output': 'JSON',
        'extensions': 'base'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
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
            return jsonify({'success': False, 'error': data.get('info', '逆地理编码失败')})
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

    if not AMAP_SERVICE_KEY:
        return jsonify({'success': False, 'error': '高德API配置缺失'})

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
        response = requests.get(url, params=params, timeout=10)
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
            return jsonify({'success': False, 'error': data.get('info', '搜索失败')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health_check():
    """健康检查端点"""
    db_status = 'connected' if get_db_connection() else 'disconnected'
    config_status = check_environment()
    
    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'configuration': 'ok' if config_status else 'missing_configs',
        'amap_web_key': 'configured' if AMAP_WEB_KEY else 'missing',
        'amap_service_key': 'configured' if AMAP_SERVICE_KEY else 'missing'
    })

# Vercel需要这个变量
app = app

# 本地开发启动（在Vercel上不会执行）
if __name__ == '__main__':
    print("=" * 60)
    print("🗺️  地图应用 - 本地开发版")
    print("=" * 60)
    
    config_ok = check_environment()
    if config_ok:
        print("✅ 环境配置检查通过")
    else:
        print("⚠️  部分配置缺失，某些功能可能无法正常工作")
    
    print(f"🔑 高德Web Key: {'✅ 已配置' if AMAP_WEB_KEY else '❌ 未配置'}")
    print(f"🔑 高德Service Key: {'✅ 已配置' if AMAP_SERVICE_KEY else '❌ 未配置'}")
    print(f"🗄️  数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("🌐 访问: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
