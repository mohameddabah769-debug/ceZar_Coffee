from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


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


