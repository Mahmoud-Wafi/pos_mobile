"""Arabic string constants for all user-facing text.

No Arabic strings should appear in logic code or services — import from here.
"""

# General
APP_TITLE = "نظام إدارة محل الموبايلات"
OK = "موافق"
CANCEL = "إلغاء"
SAVE = "حفظ"
DELETE = "حذف"
EDIT = "تعديل"
SEARCH = "بحث"
CLOSE = "إغلاق"
LOADING = "جاري التحميل..."
ERROR = "خطأ"
WARNING = "تحذير"
SUCCESS = "نجاح"
CONFIRM = "تأكيد"
YES = "نعم"
NO = "لا"

# Auth
LOGIN = "تسجيل الدخول"
LOGOUT = "تسجيل الخروج"
USERNAME = "اسم المستخدم"
PASSWORD = "كلمة المرور"
CHANGE_PASSWORD = "تغيير كلمة المرور"
OLD_PASSWORD = "كلمة المرور القديمة"
NEW_PASSWORD = "كلمة المرور الجديدة"
CONFIRM_PASSWORD = "تأكيد كلمة المرور"
LOGIN_FAILED = "اسم المستخدم أو كلمة المرور غير صحيحة"
ACCOUNT_LOCKED = "الحساب مقفل مؤقتاً بسبب محاولات دخول متعددة فاشلة"
ACCOUNT_INACTIVE = "الحساب غير مفعّل"
SESSION_EXPIRED = "انتهت الجلسة، يرجى تسجيل الدخول مجدداً"
PERMISSION_DENIED = "ليس لديك صلاحية لتنفيذ هذا الإجراء"
MANAGER_OVERRIDE = "مطلوب موافقة المدير"
MANAGER_PASSWORD = "كلمة مرور المدير"

# Navigation
DASHBOARD = "لوحة التحكم"
POS = "نقطة البيع"
INVENTORY = "المخزون"
PURCHASES = "المشتريات"
CUSTOMERS = "العملاء"
WALLETS = "المحافظ"
ACCOUNTING = "المحاسبة"
REPORTS = "التقارير"
SETTINGS = "الإعدادات"

# Roles
ROLE_MANAGER = "مدير"
ROLE_CASHIER = "كاشير"
ROLE_WALLET_EMPLOYEE = "موظف محافظ"

# Backup
BACKUP_CREATED = "تم إنشاء النسخة الاحتياطية بنجاح"
BACKUP_RESTORED = "تمت استعادة النسخة الاحتياطية بنجاح"
BACKUP_FAILED = "فشل إنشاء النسخة الاحتياطية"
RESTORE_FAILED = "فشل استعادة النسخة الاحتياطية"
BACKUP_SAFETY_COPY = "تم حفظ نسخة أمان قبل الاستعادة"

# Money
CURRENCY = "ج.م"
TOTAL = "الإجمالي"
SUBTOTAL = "المجموع الفرعي"
DISCOUNT = "الخصم"
PAID = "المدفوع"
REMAINING = "المتبقي"

# Purchases & Suppliers
SUPPLIER = "المورد"
SUPPLIERS = "الموردين"
SUPPLIER_NAME = "اسم المورد"
SUPPLIER_PHONE = "هاتف المورد"
SUPPLIER_BALANCE = "رصيد المورد"
SUPPLIER_PAYMENT = "سداد دفعة لمورد"
PURCHASE_INVOICE = "فاتورة شراء"
PURCHASE_INVOICES = "فواتير المشتريات"
NEW_PURCHASE = "فاتورة شراء جديدة"
USED_DEVICE_PURCHASE = "شراء جهاز مستعمل"
USED_DEVICE_PURCHASES = "الأجهزة المستعملة"
SELLER_NAME = "اسم البائع"
SELLER_NATIONAL_ID = "الرقم القومي للبائع"
SELLER_PHONE = "هاتف البائع"
DEVICE_CONDITION_USED = "مستعمل"
DEVICE_CONDITION_NEW = "جديد"
DECLARATION_TITLE = "إقرار وتعهد بيع هاتف مستعمل"
DECLARATION_PRINTED = "تمت طباعة الإقرار"

# Settings keys (DB)
SETTING_SHOP_NAME = "shop_name"
SETTING_SHOP_ADDRESS = "shop_address"
SETTING_SHOP_PHONE = "shop_phone"
SETTING_INVOICE_FOOTER = "invoice_footer"
SETTING_WARRANTY_TEXT = "warranty_text"
SETTING_CASHIER_DISCOUNT_LIMIT_PCT = "cashier_discount_limit_pct"
SETTING_IDLE_LOCK_MINUTES = "idle_lock_minutes"


# Login / session
LOGIN_TITLE = "تسجيل الدخول إلى النظام"
LOGIN_SUBTITLE = "أدخل اسم المستخدم وكلمة المرور للمتابعة"
LOCK_SCREEN_TITLE = "تم قفل الجلسة بسبب عدم النشاط"
LOGOUT_CONFIRM = "هل تريد تسجيل الخروج؟"
LOCK_NOW = "قفل الجلسة"
FORCE_PASSWORD_TITLE = "يجب تغيير كلمة المرور"
FORCE_PASSWORD_MSG = "أنت تستخدم كلمة المرور الافتراضية. اختر كلمة مرور جديدة للمتابعة."
PASSWORD_TOO_SHORT = "كلمة المرور الجديدة يجب أن تكون 6 خانات على الأقل"
PASSWORD_IS_DEFAULT = "لا يمكن استخدام كلمة المرور الافتراضية"
PASSWORD_MISMATCH = "كلمتا المرور غير متطابقتين"
PASSWORD_CHANGED = "تم تغيير كلمة المرور بنجاح"
ACCESS_DENIED_SCREEN = "ليس لديك صلاحية لفتح هذه الشاشة"
USER_MENU_CHANGE_PASSWORD = "تغيير كلمة المرور"
