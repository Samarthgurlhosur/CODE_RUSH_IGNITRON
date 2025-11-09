from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for
import sqlite3, qrcode, io, base64, json, uuid, datetime, os, zipfile
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS teams (
                        team_id TEXT PRIMARY KEY,
                        team_name TEXT NOT NULL,
                        members TEXT NOT NULL,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS members (
                        member_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team_id TEXT,
                        member_name TEXT,
                        check_in INTEGER DEFAULT 0,
                        check_out INTEGER DEFAULT 0,
                        snacks INTEGER DEFAULT 0,
                        dinner INTEGER DEFAULT 0
                    )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- FONT + LOGO HELPERS ----------------
def load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def fit_text(draw, text, max_width, start_size):
    size = start_size
    while size >= 14:
        font = load_bold_font(size)
        width = draw.textlength(text, font=font)
        if width <= max_width:
            return font
        size -= 2
    return load_bold_font(14)

def add_logo_to_qr(qr_img):
    """Add hackathon logo in the center of the QR (safe size)."""
    logo_path = os.path.join("static", "logo.png")
    if not os.path.exists(logo_path):
        return qr_img  # Skip if no logo found

    logo = Image.open(logo_path).convert("RGBA")
    qr_w, qr_h = qr_img.size
    logo_size = qr_w // 5  # 20% of QR width
    logo = logo.resize((logo_size, logo_size))

    pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
    qr_img.paste(logo, pos, logo)
    return qr_img

def generate_qr_with_text(team_name, qr_payload):
    """Generate QR + logo + team name below."""
    qr = qrcode.QRCode(version=4, box_size=16, border=6)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = add_logo_to_qr(qr_img)

    qr_w, qr_h = qr_img.size
    side_pad = int(qr_w * 0.12)
    bottom_area = int(qr_h * 0.40)
    new_w = qr_w + side_pad * 2
    new_h = qr_h + bottom_area
    canvas = Image.new("RGB", (new_w, new_h), "white")

    qr_x = (new_w - qr_w) // 2
    canvas.paste(qr_img, (qr_x, 0))

    draw = ImageDraw.Draw(canvas)
    text = team_name.upper()
    max_text_width = new_w - int(new_w * 0.12)
    start_font_size = max(72, qr_w // 5)
    font = fit_text(draw, text, max_text_width, start_font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (new_w - text_w) // 2
    text_y = qr_h + (bottom_area - text_h) // 2

    draw.text((text_x, text_y), text, font=font, fill="black", stroke_width=3, stroke_fill="gray")
    return canvas


# ---------------- ROUTES ----------------
@app.route('/')
def home():
    return render_template('index.html')


# ----------- REGISTER TEAM -----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        team_name = data.get('team_name', '').strip()
        members = [m.strip() for m in data.get('members', []) if m.strip()]
        if not team_name or not members:
            return jsonify({'error': 'Missing team name or members'}), 400

        team_id = str(uuid.uuid4())
        conn = get_db()
        conn.execute('INSERT INTO teams (team_id, team_name, members) VALUES (?, ?, ?)',
                     (team_id, team_name, json.dumps(members)))
        for member in members:
            conn.execute('INSERT INTO members (team_id, member_name) VALUES (?, ?)', (team_id, member))
        conn.commit()

        qr_payload = json.dumps({"team_id": team_id, "team_name": team_name, "members": members})
        qr_img = generate_qr_with_text(team_name, qr_payload)

        buf = io.BytesIO()
        qr_img.save(buf, format="PNG", dpi=(300, 300), optimize=True)
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        buf.close()

        return jsonify({'team_id': team_id, 'qr': qr_b64})
    return render_template('register.html')


# ----------- COORDINATOR DASHBOARD -----------
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


# ----------- FETCH TEAM & MEMBERS -----------
@app.route('/team/<team_id>')
def get_team(team_id):
    conn = get_db()
    cur = conn.execute('SELECT * FROM teams WHERE team_id = ?', (team_id,))
    team = cur.fetchone()
    if not team:
        return jsonify({'error': 'Team not found'})
    cur2 = conn.execute('SELECT * FROM members WHERE team_id = ?', (team_id,))
    members = [dict(row) for row in cur2.fetchall()]
    return jsonify({'team': dict(team), 'members': members})


# ----------- SHOW TEAM QR -----------
@app.route('/team_qr/<team_id>')
def team_qr(team_id):
    """Generate and show QR image for a specific team."""
    conn = get_db()
    cur = conn.execute('SELECT * FROM teams WHERE team_id = ?', (team_id,))
    team = cur.fetchone()
    if not team:
        return "Team not found", 404

    qr_payload = json.dumps({
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "members": json.loads(team["members"])
    })
    qr_img = generate_qr_with_text(team["team_name"], qr_payload)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG", dpi=(300, 300))
    buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=False)


# ----------- UPDATE MEMBER STATUS -----------
@app.route('/update_members', methods=['POST'])
def update_members():
    data = request.json
    updates = data['members']
    conn = get_db()

    for member in updates:
        conn.execute('''UPDATE members SET
                        check_in = ?, snacks = ?, dinner = ?, check_out = ?
                        WHERE member_id = ?''',
                     (member['check_in'], member['snacks'],
                      member['dinner'], member['check_out'], member['member_id']))

    team_id = conn.execute(
        'SELECT team_id FROM members WHERE member_id = ?', (updates[0]['member_id'],)
    ).fetchone()['team_id']

    conn.execute('UPDATE teams SET last_updated = ? WHERE team_id = ?',
                 (datetime.datetime.now(), team_id))
    conn.commit()

    return jsonify({'status': 'updated'})


# ----------- ADMIN VIEW -----------
@app.route('/admin')
def admin():
    conn = get_db()
    cur = conn.execute('SELECT * FROM teams ORDER BY datetime(last_updated) DESC')
    teams = [dict(row) for row in cur.fetchall()]
    teams_data = []
    for t in teams:
        cur2 = conn.execute('SELECT * FROM members WHERE team_id = ?', (t['team_id'],))
        members = [dict(row) for row in cur2.fetchall()]
        teams_data.append({'team': t, 'members': members})
    return render_template('admin.html', teams_data=teams_data)


# ----------- DELETE ONE TEAM -----------
@app.route('/delete_team/<team_id>', methods=['POST'])
def delete_team(team_id):
    conn = get_db()
    conn.execute('DELETE FROM members WHERE team_id = ?', (team_id,))
    conn.execute('DELETE FROM teams WHERE team_id = ?', (team_id,))
    conn.commit()
    return redirect(url_for('admin'))


# ----------- DELETE ALL DATA -----------
@app.route('/delete_all', methods=['POST'])
def delete_all():
    conn = get_db()
    conn.execute('DELETE FROM members')
    conn.execute('DELETE FROM teams')
    conn.commit()
    return redirect(url_for('admin'))


# ----------- EXPORT ALL QRs (ZIP) -----------
@app.route('/export_qrs')
def export_qrs():
    conn = get_db()
    cur = conn.execute('SELECT * FROM teams ORDER BY datetime(last_updated) DESC')
    teams = [dict(row) for row in cur.fetchall()]
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for t in teams:
            team_name = t['team_name']
            qr_payload = json.dumps({
                "team_id": t['team_id'],
                "team_name": team_name,
                "members": json.loads(t['members'])
            })
            qr_img = generate_qr_with_text(team_name, qr_payload)
            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format="PNG", dpi=(300, 300))
            img_buffer.seek(0)
            zipf.writestr(f"{team_name}.png", img_buffer.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name="All_QRs.zip")


# ----------- STATS API (For Dashboard) -----------
@app.route('/stats')
def stats():
    """Return total stats for check-ins, snacks, dinners, and check-outs."""
    conn = get_db()
    cur = conn.execute('''
        SELECT 
            SUM(check_in) AS check_in_total,
            SUM(snacks) AS snacks_total,
            SUM(dinner) AS dinner_total,
            SUM(check_out) AS check_out_total
        FROM members
    ''')
    stats = cur.fetchone()

    return jsonify({
        'check_in': stats['check_in_total'] or 0,
        'snacks': stats['snacks_total'] or 0,
        'dinner': stats['dinner_total'] or 0,
        'check_out': stats['check_out_total'] or 0
    })


# ----------- RUN APP -----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
