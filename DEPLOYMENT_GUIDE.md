# دليل تثبيت المشروع على Ubuntu 24.04

## المتطلبات الأساسية
- سيرفر Ubuntu 24.04
- وصول SSH للسيرفر
- قاعدة بيانات PostgreSQL (يمكن استخدام Supabase أو تثبيتها محلياً)

---

## الخطوة 1: تحديث النظام وتثبيت الأدوات الأساسية

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx
```

---

## الخطوة 2: رفع المشروع للسيرفر

### الخيار 1: من Git
```bash
cd /opt
sudo git clone https://github.com/YOUR_USERNAME/telegram_salla_app.git
sudo chown -R $USER:$USER /opt/telegram_salla_app
```

### الخيار 2: رفع يدوي عبر SCP
```bash
# من جهازك المحلي
scp -r telegram_salla_app user@your-server-ip:/opt/
```

---

## الخطوة 3: إنشاء البيئة الافتراضية وتثبيت المتطلبات

```bash
cd /opt/telegram_salla_app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### تثبيت Playwright (إذا لزم الأمر)
```bash
playwright install chromium
playwright install-deps
```

---

## الخطوة 4: إعداد ملف البيئة (.env)

```bash
cp .env.example .env
nano .env
```

### محتوى الملف:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
TELEGRAM_TOKEN=your_telegram_bot_token
SALLA_SECRET=your_salla_webhook_secret
APP_BASE_URL=https://your-domain.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=your_secure_password
SECRET_KEY=long_random_string_for_sessions_32_chars_minimum
PRIVATE_CHANNEL_ID=-1001234567890
```

---

## الخطوة 5: إعداد قاعدة البيانات

### إذا كنت تستخدم PostgreSQL محلي:
```bash
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql

# داخل psql:
CREATE DATABASE telegram_salla;
CREATE USER myuser WITH PASSWORD 'mypassword';
GRANT ALL PRIVILEGES ON DATABASE telegram_salla TO myuser;
\q
```

### تنفيذ Schema:
```bash
source venv/bin/activate
psql -h localhost -U myuser -d telegram_salla -f schema.sql
```

### تنفيذ Migrations (إن وجدت):
```bash
python apply_migration_003.py
```

---

## الخطوة 6: إعداد Systemd Service

```bash
sudo cp systemd/myapp.service /etc/systemd/system/telegram-salla.service
sudo nano /etc/systemd/system/telegram-salla.service
```

### تعديل المسارات حسب احتياجاتك:
```ini
[Unit]
Description=Telegram Salla Subscription Bot
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/telegram_salla_app
Environment="PATH=/opt/telegram_salla_app/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/telegram_salla_app/.env
ExecStart=/opt/telegram_salla_app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
```

### تفعيل وتشغيل الخدمة:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-salla
sudo systemctl start telegram-salla
sudo systemctl status telegram-salla
```

---

## الخطوة 7: إعداد Nginx كـ Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/telegram-salla
```

### محتوى الملف:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### تفعيل الموقع:
```bash
sudo ln -s /etc/nginx/sites-available/telegram-salla /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## الخطوة 8: إعداد SSL (مهم جداً للـ Webhooks)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## الخطوة 9: فتح المنافذ في Firewall

```bash
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 8000  # فقط للاختبار، يمكن إغلاقه لاحقاً
sudo ufw enable
```

---

## الأوامر المفيدة

### عرض حالة الخدمة:
```bash
sudo systemctl status telegram-salla
```

### عرض السجلات:
```bash
sudo journalctl -u telegram-salla -f
```

### إعادة تشغيل الخدمة:
```bash
sudo systemctl restart telegram-salla
```

### تحديث الكود من Git:
```bash
cd /opt/telegram_salla_app
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart telegram-salla
```

---

## استكشاف الأخطاء

### الخطأ: column s.reminder_today does not exist
تحتاج إلى تنفيذ migration لإضافة العمود:
```bash
psql -h localhost -U myuser -d telegram_salla -c "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS reminder_1_day BOOLEAN DEFAULT FALSE;"
```

### الخطأ: PRIVATE_CHANNEL_ID not found
تأكد من إضافة المتغير في ملف .env:
```env
PRIVATE_CHANNEL_ID=-1001234567890
```

### التأكد من عمل التطبيق:
```bash
curl http://localhost:8000
```

---

## ملخص الخطوات
1. تحديث النظام وتثبيت الأدوات
2. رفع المشروع
3. إنشاء venv وتثبيت requirements
4. إعداد .env
5. إعداد قاعدة البيانات
6. إعداد Systemd
7. إعداد Nginx
8. إعداد SSL
9. فتح المنافذ
