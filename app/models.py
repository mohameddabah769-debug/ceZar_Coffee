from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from .database import Base


class MenuItem(Base):
    """أصناف قائمة مشروبات وحلويات كافيه سيزر (ceZar COFFEE)."""
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(80), nullable=False, index=True)
    price = Column(Float, nullable=False)
    description = Column(String(300), nullable=True)
    is_available = Column(Boolean, default=True)


class TableOrder(Base):
    """طلبات الترابيزات الـ 25 المباشرة من مسح الـ QR Code."""
    __tablename__ = "table_orders"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, nullable=False, index=True)
    items_summary = Column(Text, nullable=False)
    total_price = Column(Float, nullable=False, default=0.0)
    status = Column(String(50), default="جديد", index=True)  # جديد | قيد التحضير | مكتمل | ملغي
    customer_name = Column(String(100), nullable=True, default="عميل سيزر")
    customer_phone = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ManagerAccount(Base):
    """حساب مدير الكافيه والمتحكم الرئيسي."""
    __tablename__ = "manager_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, default="admin")
    password = Column(String(120), nullable=False, default="123456")
    manager_name = Column(String(120), default="مدير سيزر كوفي")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
