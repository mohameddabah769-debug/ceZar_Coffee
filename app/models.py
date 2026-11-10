from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
try:
    from .database import Base
except ImportError:
    from database import Base


class MenuItem(Base):
    """أصناف قائمة مشروبات وحلويات كافيه سيزر (ceZar COFFEE)."""
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(80), nullable=False, index=True)
    price = Column(Float, nullable=False)
    cost_price = Column(Float, default=0.0)  # تكلفة الخامات المباشرة للربحية
    description = Column(String(300), nullable=True)
    is_available = Column(Boolean, default=True)


class Shift(Base):
    """إدارة شيفتات الكاشير والورديات وتقفيل الحسابات."""
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    cashier_name = Column(String(100), nullable=False, default="كاشير سيزر")
    start_time = Column(DateTime, default=datetime.utcnow, index=True)
    end_time = Column(DateTime, nullable=True)
    starting_cash = Column(Float, default=0.0)  # رصيد الدرج الافتتاحي
    total_sales = Column(Float, default=0.0)
    cash_sales = Column(Float, default=0.0)
    visa_sales = Column(Float, default=0.0)
    total_expenses = Column(Float, default=0.0)
    actual_cash = Column(Float, nullable=True)  # الكاش الفعلي عند التقفيل
    difference = Column(Float, nullable=True)   # العجز أو الزيادة
    status = Column(String(30), default="مفتوح", index=True)  # مفتوح | مغلق
    notes = Column(Text, nullable=True)


class Expense(Base):
    """مصروفات ونثريات الكافيه اليومية خلال الوردية."""
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    title = Column(String(150), nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    category = Column(String(80), default="مشتريات تشغيل")
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)


class TableOrder(Base):
    """طلبات الصالة، التيك أواي، والدليفري لكافيه سيزر."""
    __tablename__ = "table_orders"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, nullable=True, default=0, index=True)
    order_type = Column(String(30), default="صالة", index=True)  # صالة | تيك أواي | دليفري
    items_summary = Column(Text, nullable=False)
    total_price = Column(Float, nullable=False, default=0.0)
    discount_amount = Column(Float, default=0.0)
    promo_code = Column(String(50), nullable=True)
    payment_method = Column(String(30), default="كاش")  # كاش | فيزا
    status = Column(String(50), default="جديد", index=True)  # جديد | قيد التحضير | تم التقديم | ملغي | تمت التسوية
    customer_name = Column(String(100), nullable=True, default="عميل سيزر")
    customer_phone = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    
    # حقول خاصة بالدليفري
    delivery_address = Column(Text, nullable=True)
    delivery_fee = Column(Float, default=0.0)
    delivery_driver = Column(String(100), nullable=True)
    delivery_status = Column(String(50), nullable=True)  # قيد التجهيز | مع الطيار | تم التوصيل

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Reservation(Base):
    """خدمة حجز الطاولات والمناسبات المسبقة."""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(120), nullable=False)
    customer_phone = Column(String(30), nullable=False)
    table_number = Column(Integer, nullable=True)
    guests_count = Column(Integer, default=2)
    reservation_time = Column(String(50), nullable=False)
    deposit = Column(Float, default=0.0)
    status = Column(String(40), default="مؤكد", index=True)  # مؤكد | وصل وتم الجلوس | ملغي
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WaitingList(Base):
    """خدمة قائمة الانتظار للزبائن عند امتلاء الصالة."""
    __tablename__ = "waiting_list"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(120), nullable=False)
    customer_phone = Column(String(30), nullable=False)
    guests_count = Column(Integer, default=2)
    status = Column(String(40), default="قيد الانتظار", index=True)
    assigned_table = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryItem(Base):
    """إدارة مخزون المواد الخام ونواقص الكافيه."""
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)  # بن برازيلي، حليب، سكر، أكواب...
    unit = Column(String(30), default="كجم")  # كجم | لتر | علبة | كرتونة | عبوة
    current_stock = Column(Float, default=0.0)
    min_alert_stock = Column(Float, default=5.0)  # الحد الأدنى لإطلاق تنبيه النواقص
    cost_per_unit = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def cost_price(self):
        return self.cost_per_unit or 0.0

    @cost_price.setter
    def cost_price(self, val):
        self.cost_per_unit = float(val or 0.0)


class PromoCode(Base):
    """نظام الخصومات والبروموكود للزبائن والكاشير."""
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # CEZAR10, VIP, WELCOME
    discount_type = Column(String(20), default="percentage")  # percentage | fixed
    discount_value = Column(Float, nullable=False, default=10.0)  # 10% or 20 EGP
    min_order_value = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ManagerAccount(Base):
    """حسابات موظفي الكافيه (المدير، الكاشير، الباريستا)."""
    __tablename__ = "manager_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, default="admin")
    password = Column(String(120), nullable=False, default="123456")
    manager_name = Column(String(120), default="مدير سيزر كوفي")
    role = Column(String(30), default="admin")  # admin | cashier | barista
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MenuItemRecipe(Base):
    """ربط الصنف بالمواد الخام للخصم التلقائي من المخزن عند كل أوردر."""
    __tablename__ = "menu_item_recipes"

    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False, index=True)
    amount_used = Column(Float, nullable=False, default=0.02)  # مثلا 0.018 كجم بن أو 0.2 لتر حليب

    menu_item = relationship("MenuItem", backref="recipes")
    inventory_item = relationship("InventoryItem", backref="menu_recipes")


class Employee(Base):
    """شؤون الموظفين وبيانات العاملين في كافيه سيزر."""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    role = Column(String(60), default="باريستا")  # باريستا | كاشير | ويتر | شيف | كابتن صالة | نظافة
    phone = Column(String(30), nullable=True)
    salary = Column(Float, default=4000.0)  # الراتب الشهري الأساسي
    hire_date = Column(String(50), nullable=True)
    status = Column(String(30), default="نشط")  # نشط | إجازة | موقوف
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SalaryPayment(Base):
    """سجل صرف الرواتب الشهرية، السلف، والمكافآت والخصومات."""
    __tablename__ = "salary_payments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_type = Column(String(40), default="راتب شهري")  # راتب شهري | سلفة | مكافأة | خصم
    month = Column(String(30), default="2026-11")
    payment_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)


class EmployeeAttendance(Base):
    """سجل كشكول حضور وغياب وإجازات العاملين اليومي."""
    __tablename__ = "employee_attendances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    status = Column(String(30), default="حاضر")  # حاضر | غياب | إجازة | نصف يوم
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CafeSetting(Base):
    """إعدادات وهوية الكافيه الشاملة وصلاحيات تحكم المالك."""
    __tablename__ = "cafe_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(200), nullable=True)


class CafeTableConfig(Base):
    """تخصيص ترابيزات الصالة وسعاتها وأماكنها للمالك."""
    __tablename__ = "cafe_table_configs"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, unique=True, nullable=False, index=True)
    capacity = Column(Integer, default=4)
    zone = Column(String(60), default="صالة رئيسية")  # صالة رئيسية | تراس خارجي | ركن عائلي | VIP
    is_active = Column(Boolean, default=True)

class InventoryWaste(Base):
    """إدارة الهالك والعجز وتلف المواد الخام في الكافيه."""
    __tablename__ = "inventory_wastes"

    id = Column(Integer, primary_key=True, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True, index=True)
    item_name = Column(String(120), nullable=False)
    waste_type = Column(String(50), default="هالك تشغيل")  # هالك تشغيل | عجز جرد | منتهي الصلاحية | تلف بضاعة | معايرة بار | كسر أدوات
    quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(30), default="كجم")
    cost_loss = Column(Float, default=0.0)
    responsible_name = Column(String(120), default="غير محدد")
    reason = Column(Text, nullable=True)
    date = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Supplier(Base):
    """إدارة بيانات وحسابات موردي المواد الخام لكافيه سيزر."""
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)  # اسم المورد / مندوب التوريد
    company_name = Column(String(120), nullable=True)  # اسم الشركة / المطحنة / المصنع
    phone = Column(String(30), nullable=True)
    current_balance = Column(Float, default=0.0)  # المديونية / الرصيد المستحق له
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PurchaseInvoice(Base):
    """فواتير شراء وتوريد المواد الخام والمخزون للكافيه."""
    __tablename__ = "purchase_invoices"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    invoice_number = Column(String(80), nullable=True)  # رقم فاتورة التوريد
    date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    total_amount = Column(Float, nullable=False, default=0.0)
    paid_amount = Column(Float, default=0.0)  # المسدد
    remaining_amount = Column(Float, default=0.0)  # المتبقي آجل
    payment_method = Column(String(40), default="كاش من الدرج")  # كاش من الدرج | آجل | تحويل بنكي | فيزا
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PurchaseInvoiceItem(Base):
    """أصناف وخامات فاتورة التوريد لزيادة رصيد المخزن تلقائياً."""
    __tablename__ = "purchase_invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True, index=True)
    item_name = Column(String(120), nullable=False)
    quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String(30), default="كجم")
    unit_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)


class VoidAuditLog(Base):
    """سجل الرقابة الأمنية والمحذوفات لمنع التلاعب وسرقة الكاشير في الكافيه."""
    __tablename__ = "void_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)
    table_number = Column(Integer, nullable=True)
    items_summary = Column(Text, nullable=True)
    total_amount = Column(Float, default=0.0)
    reason = Column(String(150), nullable=False)  # سبب الإلغاء المعتمد
    notes = Column(Text, nullable=True)
    manager_name = Column(String(100), default="مدير الصالة")
    manager_pin_used = Column(String(50), nullable=True)
    cashier_name = Column(String(100), default="كاشير")
    action_type = Column(String(50), default="إلغاء أوردر كامل")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

