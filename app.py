from flask import Flask, render_template, jsonify, request
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# 从环境变量获取API Key（在Vercel中设置）
AMAP_WEB_KEY = os.getenv('AMAP_WEB_KEY', '11769899864085a0d06f0500c703c0a4')
AMAP_SERVICE_KEY = os.getenv('AMAP_SERVICE_KEY', 'e7ecaf4b2994df129b4c89001f60e9e3')

@app.route('/')
def index():
    """主页面"""
    return render_template('map.html', map_key=AMAP_WEB_KEY)

@app.route('/geocode')
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

# Vercel 需要这个变量
app = app