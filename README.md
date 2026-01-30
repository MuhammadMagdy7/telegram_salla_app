# نظام اشتراكات تيليجرام مع سلة (Telegram Salla Subscriptions)

نظام خفيف الموارد لإدارة اشتراكات تيليجرام وربطها بمدفوعات سلة، مصمم للعمل مباشرة على السيرفر (Systemd) بدون Docker.

## المتطلبات
- Python 3.11+
- PostgreSQL 14
- Access to Salla Merchant Account (Webhook)
- Telegram Bot Token

## الإعداد والتشغيل

1. **نسخ المشروع وإنشاء البيئة الافتراضية**:
   ```bash
   cd /opt/telegram-salla-app
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **إعداد قاعدة البيانات**:
   - تأكد من وجود المخطط (Schema) في قاعدة البيانات. يمكنك استيراده من ملف `schema.sql`:
   ```bash
   psql -U your_db_user -d your_db_name -f schema.sql
   ```

3. **ملف الإعدادات**:
   - أنشئ ملف `.env` في المجلد الرئيسي:
   ```env
   DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
   TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   SALLA_SECRET=your_salla_webhook_secret
   APP_BASE_URL=https://your-server-domain.com
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD_HASH=secretpass
   SECRET_KEY=long_random_string_for_sessions
   ```

4. **إعداد Systemd (للتشغيل التلقائي)**:
   - انسخ ملفات الخدمة من مجلد `systemd/` إلى `/etc/systemd/system/`.
   - عدل المسارات في الملفات لتطابق مسار التثبيت (`/opt/telegram-salla-app`).
   - فعل الخدمات:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now myapp.service
   sudo systemctl enable --now myapp-updater.timer
   ```

## الاستخدام

### 1. إعداد الويب هوك (Webhook) في سلة
- توجيه الويب هوك إلى: `https://your-server-domain.com/webhooks/salla`
- الأحداث المطلوبة: `Order Paid`.

### 2. البوت
- ابحث عن البوت في تيليجرام واضغط `/start`.
- شارك رقم هاتفك لربطه بالحساب.
- عند الدفع في سلة، سيقوم النظام بمطابقة رقم الهاتف وتفعيل الاشتراك وإرسال رابط القناة.

### 3. لوحة الإدارة
- الرابط: `https://your-server-domain.com/admin/login`
- لمشاهدة السجلات وإدارة الاشتراكات يدويًا.

## الملاحظات التقنية
- **الأداء**: تم ضبط `uvicorn` ليعمل بـ Worker واحد لتقليل استهلاك الرام.
- **التحديث اليومي**: يتم عبر `myapp-updater.timer` الذي يشغل سكربت بايثون مرة يومياً لفحص الاشتراكات المنتهية.
- **تجمع الاتصالات**: يستخدم `asyncpg` مع `min_size=1` و `max_size=5`.

