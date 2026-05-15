import os
import hashlib
import csv
from datetime import datetime, timedelta
from io import StringIO
from math import radians, sin, cos, sqrt, atan2
from flask import Flask, request, jsonify, session, render_template_string, make_response
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-2024'

# ============ INDIAN TIMEZONE (IST) ============
IST = timedelta(hours=5, minutes=30)

def get_indian_time():
    return datetime.utcnow() + IST

def get_indian_date():
    return (datetime.utcnow() + IST).date()

# ============ DATABASE SETUP ============
if os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============ DATABASE MODELS ============
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_indian_time)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)
    check_in_lat = db.Column(db.Float, default=0.0)
    check_in_lon = db.Column(db.Float, default=0.0)
    check_out_lat = db.Column(db.Float, default=0.0)
    check_out_lon = db.Column(db.Float, default=0.0)
    date = db.Column(db.Date, default=get_indian_date)
    status = db.Column(db.String(20), default='present')

class OfficeLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, default=0.0)
    longitude = db.Column(db.Float, default=0.0)
    radius_km = db.Column(db.Float, default=0.5)

# ============ HELPER FUNCTIONS ============
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def check_password(pwd, hashed):
    return hashlib.sha256(pwd.encode()).hexdigest() == hashed

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Please login first'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login required'}), 401
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access only'}), 403
        return f(*args, **kwargs)
    return decorated

def calculate_distance(lat1, lon1, lat2, lon2):
    if not lat1 or not lat2 or lat1 == 0 or lat2 == 0:
        return 0
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# ============ HTML TEMPLATE ============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Attendance System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 15px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 25px;
            padding: 25px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .login-container {
            max-width: 500px;
            margin: 50px auto;
        }
        h2 { color: #333; margin-bottom: 25px; text-align: center; font-size: 24px; }
        h3 { color: #555; margin: 20px 0 10px 0; font-size: 18px; }
        input {
            width: 100%;
            padding: 14px;
            margin: 10px 0;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            margin-top: 10px;
        }
        button:active { transform: scale(0.98); }
        .btn-danger { background: #dc3545; }
        .btn-success { background: #28a745; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-info { background: #17a2b8; }
        .nav-buttons {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        .nav-buttons button {
            width: auto;
            flex: 1;
            margin: 0;
            font-size: 14px;
            padding: 10px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            overflow-x: auto;
            display: block;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
            font-size: 14px;
        }
        th { background: #667eea; color: white; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin: 20px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: center;
            border-radius: 15px;
        }
        .stat-card .number { font-size: 28px; font-weight: bold; }
        .location-box {
            background: #e7f3ff;
            padding: 12px;
            border-radius: 12px;
            margin: 15px 0;
            text-align: center;
            font-size: 14px;
        }
        .message {
            margin-top: 15px;
            padding: 12px;
            border-radius: 12px;
            text-align: center;
            display: none;
        }
        .success { background: #d4edda; color: #155724; display: block; }
        .error { background: #f8d7da; color: #721c24; display: block; }
        .info { background: #d1ecf1; color: #0c5460; display: block; }
        .delete-btn { background: #dc3545; padding: 5px 10px; font-size: 12px; width: auto; margin: 0; }
        @media (max-width: 600px) {
            .container { padding: 20px; }
            .nav-buttons button { font-size: 12px; padding: 8px; }
            th, td { font-size: 11px; padding: 8px; }
        }
    </style>
</head>
<body>
<div id="app">
    <!-- LOGIN PAGE -->
    <div id="loginPage" class="container login-container">
        <h2>📋 Attendance System</h2>
        <input type="text" id="loginUsername" placeholder="Username" autocomplete="off">
        <input type="password" id="loginPassword" placeholder="Password">
        <button onclick="doLogin()">Login</button>
        <div id="loginMsg" class="message"></div>
        <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
            Contact Admin for username & password
        </div>
    </div>

    <!-- MAIN APP -->
    <div id="mainApp" style="display:none;">
        <div class="container">
            <div class="nav-buttons">
                <button onclick="showSection('dashboard')">📊 Dashboard</button>
                <button id="adminBtn" onclick="showSection('admin')" style="display:none;">👑 Admin</button>
                <button onclick="showSection('history')">📜 History</button>
                <button onclick="showSection('settings')">⚙️ Settings</button>
                <button class="btn-info" onclick="exportData()">📥 Export Excel</button>
                <button class="btn-danger" onclick="logout()">🚪 Logout</button>
            </div>
            <div id="mainContent"></div>
        </div>
    </div>
</div>

<script>
    let currentUser = null;

    async function doLogin() {
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;
        const msgDiv = document.getElementById('loginMsg');
        
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });
        const data = await res.json();
        
        if (res.ok) {
            loadMainApp();
        } else {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = data.error;
        }
    }

    async function exportData() {
        window.open('/export', '_blank');
    }

    async function loadMainApp() {
        document.getElementById('loginPage').style.display = 'none';
        document.getElementById('mainApp').style.display = 'block';
        
        const res = await fetch('/api/user-info');
        currentUser = await res.json();
        
        if (currentUser.is_admin) {
            document.getElementById('adminBtn').style.display = 'inline-block';
        }
        showSection('dashboard');
    }

    function showSection(section) {
        loadContent(section);
    }

    function getLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) reject('Not supported');
            navigator.geolocation.getCurrentPosition(
                pos => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}),
                err => reject('Please enable location')
            );
        });
    }

    async function loadContent(section) {
        const contentDiv = document.getElementById('mainContent');
        
        if (section === 'dashboard') {
            contentDiv.innerHTML = await getDashboardHTML();
            updateLocation();
            loadStats();
        } else if (section === 'admin') {
            contentDiv.innerHTML = await getAdminHTML();
            loadUsersList();
            loadAllAttendance();
            loadOfficeLocation();
        } else if (section === 'history') {
            contentDiv.innerHTML = await getHistoryHTML();
        } else if (section === 'settings') {
            contentDiv.innerHTML = getSettingsHTML();
        }
    }

    async function getDashboardHTML() {
        return `
            <h2>📊 Dashboard</h2>
            <div class="stats-grid">
                <div class="stat-card"><div class="number" id="todayStatus">--</div><div class="label">Today's Status</div></div>
                <div class="stat-card"><div class="number" id="checkInTime">--</div><div class="label">Check In Time</div></div>
                <div class="stat-card"><div class="number" id="checkOutTime">--</div><div class="label">Check Out Time</div></div>
                <div class="stat-card"><div class="number" id="monthCount">0</div><div class="label">Days Present</div></div>
            </div>
            <div id="locationStatus" class="location-box">📍 Getting location...</div>
            <div style="display: flex; gap: 10px;">
                <button id="checkInBtn" class="btn-success" onclick="markCheckIn()" style="flex:1;">✅ Check In</button>
                <button id="checkOutBtn" class="btn-warning" onclick="markCheckOut()" style="flex:1; display:none;">🔚 Check Out</button>
            </div>
            <div id="attMsg" class="message"></div>
        `;
    }

    async function getAdminHTML() {
        return `
            <h2>🔧 Admin Panel</h2>
            
            <h3>➕ Create New User</h3>
            <input type="text" id="newUsername" placeholder="Username">
            <input type="text" id="newFullName" placeholder="Full Name">
            <input type="password" id="newPassword" placeholder="Password">
            <button onclick="createUser()">Create User</button>
            <div id="createMsg" class="message"></div>
            
            <h3>📍 Set Office Location</h3>
            <input type="text" id="officeLat" placeholder="Latitude">
            <input type="text" id="officeLon" placeholder="Longitude">
            <input type="text" id="officeRadius" placeholder="Radius (km)" value="0.5">
            <button onclick="saveOfficeLocation()">Save Location</button>
            <button class="btn-info" onclick="useCurrentLocation()">Use My Location</button>
            
            <h3>👥 All Users</h3>
            <div id="usersList"></div>
            
            <h3>📅 All Attendance Records</h3>
            <div id="allAttendanceTable"></div>
        `;
    }

    async function getHistoryHTML() {
        const res = await fetch('/api/my-attendance');
        const data = await res.json();
        
        if (data.attendance && data.attendance.length > 0) {
            let html = '能able<thead><tr><th>Date</th><th>Check In</th><th>Check Out</th><th>Check In Location</th><th>Check Out Location</th><th>Status</th></tr></thead><tbody>';
            for (let a of data.attendance) {
                const statusBadge = a.status === 'late' ? '🕐 Late' : '✅ On Time';
                const checkInLoc = a.check_in_lat ? `${a.check_in_lat.toFixed(4)}, ${a.check_in_lon.toFixed(4)}` : '-';
                const checkOutLoc = a.check_out_lat ? `${a.check_out_lat.toFixed(4)}, ${a.check_out_lon.toFixed(4)}` : '-';
                html += `<tr>
                    <td>${new Date(a.date).toLocaleDateString()}</td>
                    <td>${a.check_in_time || '-'}</td>
                    <td>${a.check_out_time || '-'}</td>
                    <td>${checkInLoc}</td>
                    <td>${checkOutLoc}</td>
                    <td>${statusBadge}</td>
                </tr>`;
            }
            html += '</tbody></table>';
            return `<h2>📜 My Attendance History</h2>${html}`;
        } else {
            return `<h2>📜 My Attendance History</h2><p>No attendance records found.</p>`;
        }
    }

    function getSettingsHTML() {
        return `
            <h2>⚙️ Settings</h2>
            <h3>Change Password</h3>
            <input type="password" id="oldPassword" placeholder="Current Password">
            <input type="password" id="newPassword1" placeholder="New Password">
            <input type="password" id="newPassword2" placeholder="Confirm Password">
            <button onclick="changePassword()">Update Password</button>
            <div id="settingsMsg" class="message"></div>
        `;
    }

    async function updateLocation() {
        try {
            const loc = await getLocation();
            document.getElementById('locationStatus').innerHTML = `📍 Your location: ${loc.lat.toFixed(6)}, ${loc.lon.toFixed(6)}`;
            return loc;
        } catch(e) {
            document.getElementById('locationStatus').innerHTML = `⚠️ ${e} - Enable location for attendance`;
            return null;
        }
    }

    async function loadStats() {
        const res = await fetch('/api/today-status');
        const data = await res.json();
        document.getElementById('todayStatus').innerHTML = data.status;
        document.getElementById('checkInTime').innerHTML = data.check_in_time || '--';
        document.getElementById('checkOutTime').innerHTML = data.check_out_time || '--';
        document.getElementById('monthCount').innerHTML = data.month_days;
        
        if (data.checked_in && !data.checked_out) {
            document.getElementById('checkInBtn').style.display = 'none';
            document.getElementById('checkOutBtn').style.display = 'block';
        } else if (data.checked_out) {
            document.getElementById('checkInBtn').style.display = 'block';
            document.getElementById('checkOutBtn').style.display = 'none';
            document.getElementById('checkInBtn').innerHTML = '✅ Check In (Already Completed)';
            document.getElementById('checkInBtn').disabled = true;
        } else {
            document.getElementById('checkInBtn').style.display = 'block';
            document.getElementById('checkOutBtn').style.display = 'none';
            document.getElementById('checkInBtn').disabled = false;
            document.getElementById('checkInBtn').innerHTML = '✅ Check In';
        }
    }

    async function markCheckIn() {
        const msgDiv = document.getElementById('attMsg');
        msgDiv.className = 'message info';
        msgDiv.innerHTML = '📍 Getting your location...';
        
        try {
            const loc = await getLocation();
            if (!loc) {
                msgDiv.className = 'message error';
                msgDiv.innerHTML = '❌ Please enable location access';
                return;
            }
            msgDiv.innerHTML = '✅ Submitting check-in...';
            const res = await fetch('/api/check-in', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({latitude: loc.lat, longitude: loc.lon})
            });
            const data = await res.json();
            
            if (res.ok) {
                msgDiv.className = 'message success';
                msgDiv.innerHTML = '✅ ' + data.message;
                loadStats();
            } else {
                msgDiv.className = 'message error';
                msgDiv.innerHTML = '❌ ' + data.error;
            }
        } catch(e) {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = '❌ ' + e;
        }
        setTimeout(() => msgDiv.style.display = 'none', 5000);
    }

    async function markCheckOut() {
        const msgDiv = document.getElementById('attMsg');
        msgDiv.className = 'message info';
        msgDiv.innerHTML = '📍 Getting your location...';
        
        try {
            const loc = await getLocation();
            if (!loc) {
                msgDiv.className = 'message error';
                msgDiv.innerHTML = '❌ Please enable location access';
                return;
            }
            msgDiv.innerHTML = '✅ Submitting check-out...';
            const res = await fetch('/api/check-out', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({latitude: loc.lat, longitude: loc.lon})
            });
            const data = await res.json();
            
            if (res.ok) {
                msgDiv.className = 'message success';
                msgDiv.innerHTML = '✅ ' + data.message;
                loadStats();
            } else {
                msgDiv.className = 'message error';
                msgDiv.innerHTML = '❌ ' + data.error;
            }
        } catch(e) {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = '❌ ' + e;
        }
        setTimeout(() => msgDiv.style.display = 'none', 5000);
    }

    async function loadUsersList() {
        const res = await fetch('/api/admin/users');
        const data = await res.json();
        
        let html = '能able<thead><tr><th>Username</th><th>Full Name</th><th>Created</th><th>Action</th></tr></thead><tbody>';
        for (let u of data.users) {
            const isCurrentUser = u.id === currentUser.id;
            const showDelete = (!u.is_admin && !isCurrentUser);
            
            html += `<tr>
                <td>${u.username}${u.is_admin ? ' 👑' : ''}${isCurrentUser ? ' (You)' : ''}</td>
                <td>${u.full_name}</td>
                <td>${new Date(u.created_at).toLocaleDateString()}</td>
                <td>${showDelete ? `<button class="delete-btn" onclick="deleteUser(${u.id}, '${u.username}')">🗑 Delete</button>` : '-'}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        document.getElementById('usersList').innerHTML = html;
    }

    async function deleteUser(userId, username) {
        if (confirm(`⚠️ Are you sure you want to delete user "${username}"?\n\nThis will also delete ALL their attendance records!\n\nThis action cannot be undone.`)) {
            const res = await fetch(`/api/admin/delete-user/${userId}`, {
                method: 'DELETE',
                headers: {'Content-Type': 'application/json'}
            });
            const data = await res.json();
            
            if (res.ok) {
                alert('✅ ' + data.message);
                loadUsersList();
                loadAllAttendance();
            } else {
                alert('❌ ' + data.error);
            }
        }
    }

    async function loadAllAttendance() {
        const res = await fetch('/api/admin/all-attendance');
        const data = await res.json();
        
        if (data.attendance && data.attendance.length > 0) {
            let html = '能able<thead><tr><th>Date</th><th>User</th><th>Check In</th><th>Check Out</th><th>Check In Location</th></tr></thead><tbody>';
            for (let a of data.attendance) {
                const statusBadge = a.status === 'late' ? '🕐 Late' : '✅ On Time';
                const checkInLoc = a.check_in_lat ? `${a.check_in_lat.toFixed(4)}, ${a.check_in_lon.toFixed(4)}` : '-';
                html += `<tr>
                    <td>${new Date(a.date).toLocaleDateString()} ${statusBadge}</td>
                    <td>${a.user_name}${a.is_admin ? ' 👑' : ''}</td>
                    <td>${a.check_in_time || '-'}</td>
                    <td>${a.check_out_time || '-'}</td>
                    <td>${checkInLoc}</td>
                </tr>`;
            }
            html += '</tbody></table>';
            document.getElementById('allAttendanceTable').innerHTML = html;
        } else {
            document.getElementById('allAttendanceTable').innerHTML = '<p>No records found.</p>';
        }
    }

    async function loadOfficeLocation() {
        const res = await fetch('/api/admin/office-location');
        const data = await res.json();
        if (data.latitude && data.latitude !== 0) {
            document.getElementById('officeLat').value = data.latitude;
            document.getElementById('officeLon').value = data.longitude;
            document.getElementById('officeRadius').value = data.radius;
        }
    }

    async function createUser() {
        const username = document.getElementById('newUsername').value;
        const full_name = document.getElementById('newFullName').value;
        const password = document.getElementById('newPassword').value;
        const msgDiv = document.getElementById('createMsg');
        
        if (!username || !full_name || !password) {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = 'Please fill all fields';
            return;
        }
        
        const res = await fetch('/api/admin/create-user', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, full_name, password})
        });
        const data = await res.json();
        
        if (res.ok) {
            msgDiv.className = 'message success';
            msgDiv.innerHTML = '✅ User created! Username: ' + username;
            document.getElementById('newUsername').value = '';
            document.getElementById('newFullName').value = '';
            document.getElementById('newPassword').value = '';
            loadUsersList();
        } else {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = '❌ ' + data.error;
        }
        setTimeout(() => msgDiv.style.display = 'none', 3000);
    }

    async function saveOfficeLocation() {
        const lat = parseFloat(document.getElementById('officeLat').value);
        const lon = parseFloat(document.getElementById('officeLon').value);
        const radius = parseFloat(document.getElementById('officeRadius').value);
        
        if (isNaN(lat) || isNaN(lon)) {
            alert('Please enter valid latitude and longitude');
            return;
        }
        
        const res = await fetch('/api/admin/set-location', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({latitude: lat, longitude: lon, radius: radius})
        });
        const data = await res.json();
        alert(data.message);
    }

    async function useCurrentLocation() {
        try {
            const loc = await getLocation();
            if (loc) {
                document.getElementById('officeLat').value = loc.lat;
                document.getElementById('officeLon').value = loc.lon;
                alert('✅ Location captured! Click Save Location to save.');
            }
        } catch(e) {
            alert('Could not get location');
        }
    }

    async function changePassword() {
        const oldPwd = document.getElementById('oldPassword').value;
        const newPwd1 = document.getElementById('newPassword1').value;
        const newPwd2 = document.getElementById('newPassword2').value;
        const msgDiv = document.getElementById('settingsMsg');
        
        if (newPwd1 !== newPwd2) {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = 'New passwords do not match';
            return;
        }
        
        const res = await fetch('/api/change-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({old_password: oldPwd, new_password: newPwd1})
        });
        const data = await res.json();
        
        if (res.ok) {
            msgDiv.className = 'message success';
            msgDiv.innerHTML = data.message;
            setTimeout(() => logout(), 2000);
        } else {
            msgDiv.className = 'message error';
            msgDiv.innerHTML = data.error;
        }
    }

    async function logout() {
        await fetch('/api/logout', {method: 'POST'});
        location.reload();
    }
</script>
</body>
</html>
'''

# ============ API ROUTES ============
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not check_password(data['password'], user.password):
        return jsonify({'error': 'Invalid username or password'}), 401
    
    session['user_id'] = user.id
    return jsonify({'message': 'Logged in', 'is_admin': user.is_admin})

@app.route('/api/user-info')
@login_required
def user_info():
    user = User.query.get(session['user_id'])
    return jsonify({
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'is_admin': user.is_admin
    })

@app.route('/api/check-in', methods=['POST'])
@login_required
def check_in():
    data = request.json
    user_id = session['user_id']
    today = get_indian_date()
    indian_now = get_indian_time()
    
    existing = Attendance.query.filter_by(user_id=user_id, date=today).first()
    if existing and existing.check_in:
        return jsonify({'error': 'Already checked in today! Please check out first.'}), 400
    
    office = OfficeLocation.query.first()
    if office and office.latitude and office.latitude != 0:
        dist = calculate_distance(data['latitude'], data['longitude'], office.latitude, office.longitude)
        if dist > office.radius_km:
            return jsonify({'error': f'You are {dist:.2f}km away. Must be within {office.radius_km}km of office.'}), 400
    
    is_late = indian_now.hour > 9 or (indian_now.hour == 9 and indian_now.minute > 30)
    
    attendance = Attendance(
        user_id=user_id,
        check_in=indian_now,
        check_in_lat=data['latitude'],
        check_in_lon=data['longitude'],
        date=today,
        status='late' if is_late else 'present'
    )
    db.session.add(attendance)
    db.session.commit()
    
    return jsonify({'message': f'Checked in at {indian_now.strftime("%I:%M %p")} IST!'})

@app.route('/api/check-out', methods=['POST'])
@login_required
def check_out():
    data = request.json
    user_id = session['user_id']
    today = get_indian_date()
    indian_now = get_indian_time()
    
    attendance = Attendance.query.filter_by(user_id=user_id, date=today).first()
    if not attendance or not attendance.check_in:
        return jsonify({'error': 'No check-in found for today!'}), 400
    
    if attendance.check_out:
        return jsonify({'error': 'Already checked out today!'}), 400
    
    attendance.check_out = indian_now
    attendance.check_out_lat = data['latitude']
    attendance.check_out_lon = data['longitude']
    db.session.commit()
    
    return jsonify({'message': f'Checked out at {indian_now.strftime("%I:%M %p")} IST!'})

@app.route('/api/today-status')
@login_required
def today_status():
    user_id = session['user_id']
    today = get_indian_date()
    attendance = Attendance.query.filter_by(user_id=user_id, date=today).first()
    month_count = Attendance.query.filter_by(user_id=user_id).count()
    
    if attendance and attendance.check_in and attendance.check_out:
        return jsonify({
            'status': 'Completed',
            'check_in_time': attendance.check_in.strftime('%I:%M %p'),
            'check_out_time': attendance.check_out.strftime('%I:%M %p'),
            'checked_in': True,
            'checked_out': True,
            'month_days': month_count
        })
    elif attendance and attendance.check_in:
        return jsonify({
            'status': 'Checked In',
            'check_in_time': attendance.check_in.strftime('%I:%M %p'),
            'check_out_time': '--',
            'checked_in': True,
            'checked_out': False,
            'month_days': month_count
        })
    else:
        return jsonify({
            'status': 'Not Marked',
            'check_in_time': '--',
            'check_out_time': '--',
            'checked_in': False,
            'checked_out': False,
            'month_days': month_count
        })

@app.route('/api/my-attendance')
@login_required
def my_attendance():
    user_id = session['user_id']
    records = Attendance.query.filter_by(user_id=user_id).order_by(Attendance.date.desc()).all()
    
    result = []
    for r in records:
        result.append({
            'date': r.date.isoformat(),
            'check_in_time': r.check_in.strftime('%I:%M %p') if r.check_in else None,
            'check_out_time': r.check_out.strftime('%I:%M %p') if r.check_out else None,
            'check_in_lat': r.check_in_lat,
            'check_in_lon': r.check_in_lon,
            'check_out_lat': r.check_out_lat,
            'check_out_lon': r.check_out_lon,
            'status': r.status
        })
    return jsonify({'attendance': result})

@app.route('/api/admin/users')
@admin_required
def get_users():
    users = User.query.all()
    return jsonify({
        'users': [{
            'id': u.id,
            'username': u.username,
            'full_name': u.full_name,
            'is_admin': u.is_admin,
            'created_at': u.created_at.isoformat()
        } for u in users]
    })

@app.route('/api/admin/create-user', methods=['POST'])
@admin_required
def create_user():
    data = request.json
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = User(
        username=data['username'],
        full_name=data['full_name'],
        password=hash_password(data['password']),
        is_admin=False
    )
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'message': 'User created successfully!'})

@app.route('/api/admin/delete-user/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.id == session['user_id']:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    if user.is_admin:
        return jsonify({'error': 'Cannot delete admin users'}), 400
    
    Attendance.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'message': f'User {user.username} deleted successfully!'})

@app.route('/api/admin/all-attendance')
@admin_required
def all_attendance():
    records = Attendance.query.order_by(Attendance.date.desc()).all()
    users = {u.id: {'username': u.username, 'is_admin': u.is_admin} for u in User.query.all()}
    
    result = []
    for r in records:
        user_info = users.get(r.user_id, {'username': 'Unknown', 'is_admin': False})
        result.append({
            'date': r.date.isoformat(),
            'user_name': user_info['username'],
            'is_admin': user_info['is_admin'],
            'check_in_time': r.check_in.strftime('%I:%M %p') if r.check_in else None,
            'check_out_time': r.check_out.strftime('%I:%M %p') if r.check_out else None,
            'check_in_lat': r.check_in_lat,
            'check_in_lon': r.check_in_lon,
            'status': r.status
        })
    return jsonify({'attendance': result})

@app.route('/api/admin/set-location', methods=['POST'])
@admin_required
def set_location():
    data = request.json
    office = OfficeLocation.query.first()
    if not office:
        office = OfficeLocation()
        db.session.add(office)
    office.latitude = data['latitude']
    office.longitude = data['longitude']
    office.radius_km = data.get('radius', 0.5)
    db.session.commit()
    return jsonify({'message': 'Office location saved!'})

@app.route('/api/admin/office-location')
@admin_required
def get_office_location():
    office = OfficeLocation.query.first()
    return jsonify({
        'latitude': office.latitude if office else None,
        'longitude': office.longitude if office else None,
        'radius': office.radius_km if office else 0.5
    })

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    user = User.query.get(session['user_id'])
    
    if not check_password(data['old_password'], user.password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    user.password = hash_password(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password changed! Please login again.'})

@app.route('/export')
@login_required
def export_data():
    records = Attendance.query.order_by(Attendance.date.desc()).all()
    users = {u.id: u.username for u in User.query.all()}
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Employee', 'Check In Time', 'Check Out Time', 'Check In Latitude', 'Check In Longitude', 'Status'])
    
    for r in records:
        writer.writerow([
            r.date,
            users.get(r.user_id, 'Unknown'),
            r.check_in.strftime('%Y-%m-%d %H:%M:%S') if r.check_in else '',
            r.check_out.strftime('%Y-%m-%d %H:%M:%S') if r.check_out else '',
            r.check_in_lat,
            r.check_in_lon,
            r.status
        ])
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=attendance_{get_indian_date()}.csv'
    return response

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

# ============ INITIALIZE DATABASE ============
with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin = User(
            username='admin',
            full_name='Administrator',
            password=hash_password('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Admin user created!')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
