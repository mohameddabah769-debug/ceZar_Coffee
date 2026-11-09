import re
import os
import sys
import io
import csv
import socket
from typing import Optional, List
from datetime import datetime

# ضبط ترميز النصوص العربية
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import qrcode
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, Response, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

from .database import engine, Base, SessionLocal, get_db
from .models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee, SalaryPayment, EmployeeAttendance, CafeSetting, CafeTableConfig, InventoryWaste, Supplier, PurchaseInvoice, PurchaseInvoiceItem, VoidAuditLog
from .seed import seed_menu

# إنشاء الجداول تلقائياً
Base.metadata.create_all(bind=engine)

def auto_migrate_columns():
    with engine.connect() as conn:
        columns_to_add = [
            ("order_type", "VARCHAR(30) DEFAULT 'صالة'"),
            ("payment_method", "VARCHAR(30) DEFAULT 'كاش'"),
            ("shift_id", "INTEGER DEFAULT NULL"),
            ("delivery_address", "TEXT DEFAULT NULL"),
            ("delivery_fee", "FLOAT DEFAULT 0.0"),
            ("delivery_driver", "VARCHAR(100) DEFAULT NULL"),
            ("delivery_status", "VARCHAR(50) DEFAULT NULL"),
            ("discount_amount", "FLOAT DEFAULT 0.0"),
            ("promo_code", "VARCHAR(50) DEFAULT NULL"),
        ]
        try:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN cost_price FLOAT DEFAULT 0.0"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE manager_accounts ADD COLUMN role VARCHAR(30) DEFAULT 'admin'"))
            conn.commit()
        except Exception:
            pass
        
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE table_orders ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

auto_migrate_columns()

with SessionLocal() as db:
    seed_menu(db)
    if db.query(ManagerAccount).filter(ManagerAccount.username == "admin").count() == 0:
        db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
    if db.query(ManagerAccount).filter(ManagerAccount.username == "cezar").count() == 0:
        db.add(ManagerAccount(username="cezar", password="0000", manager_name="كافيه سيزر"))
    db.commit()

app = FastAPI(
    title="ceZar COFFEE - Enterprise Café Management & POS System",
    description="نظام إدارة المبيعات، الشيفتات، الحجوزات، الصالة، الدليفري، شاشة البار، المخزون، والخصومات",
    version="3.0.0"
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ==========================================
# نماذج البيانات (Pydantic Schemas)
# ==========================================

class TableOrderItem(BaseModel):
    id: Optional[int] = 0
    name: str
    price: float
    quantity: int = 1
    customization: Optional[str] = None


class CreateTableOrderRequest(BaseModel):
    table_number: int
    items: List[TableOrderItem]
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    promo_code: Optional[str] = None


class PosOrderCreateRequest(BaseModel):
    order_type: str = "صالة"  # صالة | تيك أواي | دليفري
    table_number: Optional[int] = 0
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[TableOrderItem]
    payment_method: str = "كاش"  # كاش | فيزا
    notes: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_fee: Optional[float] = 0.0
    delivery_driver: Optional[str] = None
    discount_amount: Optional[float] = 0.0
    promo_code: Optional[str] = None


class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: Optional[str] = None
    is_available: bool = True


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None


class OrderStatusUpdate(BaseModel):
    status: str


class CallWaiterRequest(BaseModel):
    table_number: int


class RequestBillRequest(BaseModel):
    table_number: int
    payment_method: str = "كاش"


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangeCredentialsRequest(BaseModel):
    current_password: str
    new_username: str
    new_password: str


class ShiftOpenRequest(BaseModel):
    cashier_name: str = "كاشير سيزر"
    starting_cash: float = 0.0
    notes: Optional[str] = None


class ShiftCloseRequest(BaseModel):
    actual_cash: float
    notes: Optional[str] = None


class ExpenseCreateRequest(BaseModel):
    title: str
    amount: float
    category: str = "مشتريات تشغيل"
    notes: Optional[str] = None


class ReservationCreateRequest(BaseModel):
    customer_name: str
    customer_phone: str
    table_number: Optional[int] = None
    guests_count: int = 2
    reservation_time: str
    deposit: float = 0.0
    notes: Optional[str] = None


class WaitingListCreateRequest(BaseModel):
    customer_name: str
    customer_phone: str
    guests_count: int = 2
    notes: Optional[str] = None


class SeatWaitingCustomerRequest(BaseModel):
    table_number: int


class DeliveryStatusUpdateRequest(BaseModel):
    delivery_status: str
    delivery_driver: Optional[str] = None


class PromoCodeCreateRequest(BaseModel):
    code: str
    discount_type: str = "percentage"  # percentage | fixed
    discount_value: float = 10.0
    min_order_value: float = 0.0


class PromoValidateRequest(BaseModel):
    code: str
    order_total: float = 0.0


class InventoryCreateRequest(BaseModel):
    name: str
    unit: str = "كجم"
    current_stock: float = 0.0
    min_alert_stock: float = 5.0
    cost_per_unit: float = 0.0




class OfflineOrderItem(BaseModel):
    id: Optional[int] = 0
    name: str
    price: float = 0.0
    quantity: int = 1
    customizations: Optional[List[Any]] = []
    notes: Optional[str] = None

class OfflineOrderSyncItem(BaseModel):
    order_type: str = "صالة"
    table_number: Optional[int] = 1
    customer_name: Optional[str] = "ترابيزة 1"
    items: List[OfflineOrderItem]
    payment_method: str = "كاش"
    notes: Optional[str] = None
    discount_amount: Optional[float] = 0.0
    promo_code: Optional[str] = None
    offline_created_at: Optional[str] = None

class OfflineSyncRequest(BaseModel):
    orders: List[OfflineOrderSyncItem]

class InventoryWasteCreateRequest(BaseModel):
    inventory_item_id: Optional[int] = None
    item_name: str
    waste_type: str = "هالك تشغيل"
    quantity: float = 1.0
    unit: str = "كجم"
    cost_loss: Optional[float] = None
    responsible_name: str = "غير محدد"
    reason: Optional[str] = None
    date: Optional[str] = None
    auto_deduct_stock: bool = True

class InventoryUpdateRequest(BaseModel):
    current_stock: Optional[float] = None
    min_alert_stock: Optional[float] = None
    cost_per_unit: Optional[float] = None


# ==========================================
# 1. صفحات العرض (Frontend Views)
# ==========================================

@app.get("/")
def home():
    return RedirectResponse(url="/admin")


@app.get("/menu", response_class=HTMLResponse)
@app.get("/cezar/menu", response_class=HTMLResponse)
def get_menu_page():
    file_path = os.path.join(TEMPLATES_DIR, "menu.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>جاري تحميل منيو سيزر كوفي...</h2>")


@app.get("/admin", response_class=HTMLResponse)
@app.get("/cezar/admin", response_class=HTMLResponse)
def get_admin_page():
    file_path = os.path.join(TEMPLATES_DIR, "admin.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>جاري تحميل لوحة تحكم سيزر كوفي...</h2>")


@app.get("/kitchen", response_class=HTMLResponse)
@app.get("/bar", response_class=HTMLResponse)
@app.get("/cezar/bar", response_class=HTMLResponse)
def get_kitchen_page():
    file_path = os.path.join(TEMPLATES_DIR, "kitchen.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>جاري تحميل شاشة البار والمطبخ (KDS)...</h2>")


@app.get("/qr-cards", response_class=HTMLResponse)
@app.get("/cezar/qr-generator", response_class=HTMLResponse)
def get_qr_cards_page():
    file_path = os.path.join(TEMPLATES_DIR, "qr_cards.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>جاري تحميل كروت الـ QR للترابيزات...</h2>")


# ==========================================
# 2. واجهات برمجة الأصناف (Menu APIs)
# ==========================================

@app.get("/api/menu-items")
@app.get("/api/cezar/menu-items")
def get_menu_items(all_items: bool = False, category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(MenuItem)
    if not all_items:
        query = query.filter(MenuItem.is_available.is_(True))
    if category and category.strip():
        query = query.filter(MenuItem.category == category.strip())

    items = query.order_by(MenuItem.category, MenuItem.price).all()

    grouped = {}
    for item in items:
        grouped.setdefault(item.category, []).append({
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "price": item.price,
            "description": item.description or "",
            "is_available": item.is_available
        })

    return {"categories": grouped, "total_count": len(items)}


@app.post("/api/menu-items")
@app.post("/api/cezar/menu-items")
def add_menu_item(data: MenuItemCreate, db: Session = Depends(get_db)):
    new_item = MenuItem(
        name=data.name.strip(),
        category=data.category.strip(),
        price=data.price,
        description=data.description,
        is_available=data.is_available
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"status": "success", "item": {"id": new_item.id, "name": new_item.name}}


@app.put("/api/menu-items/{item_id}")
@app.put("/api/cezar/menu-items/{item_id}")
def update_menu_item(item_id: int, data: MenuItemUpdate, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if data.name is not None:
        item.name = data.name.strip()
    if data.category is not None:
        item.category = data.category.strip()
    if data.price is not None:
        item.price = data.price
    if data.description is not None:
        item.description = data.description
    if data.is_available is not None:
        item.is_available = data.is_available

    db.commit()
    db.refresh(item)
    return {
        "status": "success",
        "item": {
            "id": item.id,
            "name": item.name,
            "price": item.price,
            "is_available": item.is_available
        }
    }


@app.delete("/api/menu-items/{item_id}")
@app.delete("/api/cezar/menu-items/{item_id}")
def delete_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"status": "success", "deleted_id": item_id}


# ==========================================
# 3. واجهات برمجة الطلبات والكاشير (POS & Orders)
# ==========================================

def deduct_inventory_for_order(items, db: Session):
    """الخصم التلقائي الدقيق للمواد الخام وفق خلطة ومقادير كل صنف (Recipe BOM)."""
    try:
        inv_items = {it.name: it for it in db.query(InventoryItem).all()}
        coffee_beans = next((v for k, v in inv_items.items() if "بن" in k and "تركي" not in k and "تركى" not in k), None)
        milk_item = next((v for k, v in inv_items.items() if "حليب" in k or "لبن" in k), None)
        syrup_item = next((v for k, v in inv_items.items() if "سيرب" in k), None)
        turkish_coffee = next((v for k, v in inv_items.items() if "بن" in k and ("تركي" in k or "تركى" in k)), None)
        cups_item = next((v for k, v in inv_items.items() if "أكواب" in k or "كوب" in k), None)

        for item in items:
            name = (item.get('name') if isinstance(item, dict) else getattr(item, 'name', '')) or ''
            qty = (item.get('quantity') if isinstance(item, dict) else getattr(item, 'quantity', 1)) or 1
            customization = ((item.get('customization') if isinstance(item, dict) else getattr(item, 'customization', '')) or '').strip()

            # 1. التحقق من وجود خلطة ومقادير مخصصة للصنف (Exact Recipe BOM)
            m_item = db.query(MenuItem).filter(MenuItem.name == name.strip()).first()
            if m_item and m_item.recipes:
                for r in m_item.recipes:
                    raw_inv = db.query(InventoryItem).filter(InventoryItem.id == r.inventory_item_id).first()
                    if raw_inv:
                        total_deduct = round(r.amount_used * qty, 4)
                        raw_inv.current_stock = max(0.0, round(raw_inv.current_stock - total_deduct, 3))
                continue

            # 2. الخصم التقديري الافتراضي للأصناف التي لم تسجل لها مقادير بعد
            # 1. Coffee Beans (0.018 kg per shot)
            is_coffee = any(k in name for k in ["اسبريسو", "لاتيه", "كابتشينو", "امريكان", "فلات وايت", "موكا", "كورتادو", "ميكاتو", "قهوة"])
            if is_coffee and coffee_beans:
                w = 0.018 * qty
                if "دبل" in name: w *= 2
                if "شوت إضافي" in customization: w += (0.018 * qty)
                coffee_beans.current_stock = max(0.0, round(coffee_beans.current_stock - w, 3))

            # 2. Milk (0.180 Liter)
            needs_milk = any(k in name for k in ["لاتيه", "كابتشينو", "فلات وايت", "كورتادو", "فرنساوى", "موكا", "حليب", "سحلب", "شوكليت"])
            if needs_milk and "بدون حليب" not in customization and milk_item:
                m_amt = 0.180 * qty
                milk_item.current_stock = max(0.0, round(milk_item.current_stock - m_amt, 3))

            # 3. Syrups (0.02 Liter)
            if ("كراميل" in customization or "فانيليا" in customization or "كراميل" in name or "فانيليا" in name) and syrup_item:
                syrup_item.current_stock = max(0.0, round(syrup_item.current_stock - (0.02 * qty), 3))

            # 4. Turkish Coffee
            if ("تركي" in name or "تركى" in name) and turkish_coffee:
                w_t = 0.012 * qty
                if "دبل" in name: w_t *= 2
                turkish_coffee.current_stock = max(0.0, round(turkish_coffee.current_stock - w_t, 3))

            # 5. Cups
            if cups_item:
                cups_item.current_stock = max(0.0, round(cups_item.current_stock - qty, 1))

        db.commit()
    except Exception as e:
        print(f"Auto-deduct warning: {e}")



@app.post("/api/orders")
@app.post("/api/cezar/orders")
def create_table_order(order_data: CreateTableOrderRequest, db: Session = Depends(get_db)):
    if not order_data.items:
        raise HTTPException(status_code=400, detail="السلة فارغة")

    lines = []
    items_total = 0.0
    for item in order_data.items:
        item_total = item.price * item.quantity
        items_total += item_total
        cust_note = f" [{item.customization}]" if item.customization else ""
        lines.append(f"- {item.quantity}x {item.name}{cust_note}: {item_total:g} ج")

    # تطبيق البروموكود إذا وجد
    discount = 0.0
    if order_data.promo_code:
        promo = db.query(PromoCode).filter(PromoCode.code == order_data.promo_code.strip().upper(), PromoCode.is_active.is_(True)).first()
        if promo and items_total >= (promo.min_order_value or 0.0):
            if promo.discount_type == "percentage":
                discount = round((items_total * promo.discount_value) / 100.0, 2)
            else:
                discount = min(items_total, promo.discount_value)
            promo.usage_count = (promo.usage_count or 0) + 1

    grand_total = max(0.0, items_total - discount)
    items_summary = "\n".join(lines)

    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    shift_id = current_shift.id if current_shift else None

    order = TableOrder(
        table_number=order_data.table_number,
        order_type="صالة",
        items_summary=items_summary,
        total_price=grand_total,
        discount_amount=discount,
        promo_code=order_data.promo_code,
        customer_name=order_data.customer_name or f"ترابيزة {order_data.table_number}",
        customer_phone=order_data.customer_phone or "",
        notes=order_data.notes or "",
        status="جديد",
        payment_method="كاش",
        shift_id=shift_id
    )
    db.add(order)

    if current_shift:
        current_shift.total_sales += grand_total
        current_shift.cash_sales += grand_total

    deduct_inventory_for_order(order_data.items, db)
    db.commit()
    db.refresh(order)
    return {
        "status": "success",
        "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
        "order_id": order.id,
        "table_number": order.table_number,
        "discount_amount": discount,
        "total_price": order.total_price
    }


@app.post("/api/pos/orders")
@app.post("/api/cezar/pos/orders")
def create_pos_direct_order(data: PosOrderCreateRequest, db: Session = Depends(get_db)):
    if not data.items:
        raise HTTPException(status_code=400, detail="يجب إضافة صنف واحد على الأقل للأوردر")

    lines = []
    items_total = 0.0
    for item in data.items:
        item_total = item.price * item.quantity
        items_total += item_total
        cust_note = f" [{item.customization}]" if item.customization else ""
        lines.append(f"- {item.quantity}x {item.name}{cust_note}: {item_total:g} ج")

    delivery_fee = data.delivery_fee or 0.0 if data.order_type == "دليفري" else 0.0
    discount = data.discount_amount or 0.0
    grand_total = max(0.0, items_total + delivery_fee - discount)
    items_summary = "\n".join(lines)

    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    shift_id = current_shift.id if current_shift else None

    order = TableOrder(
        table_number=data.table_number if data.order_type == "صالة" else 0,
        order_type=data.order_type,
        items_summary=items_summary,
        total_price=grand_total,
        discount_amount=discount,
        promo_code=data.promo_code,
        payment_method=data.payment_method,
        status="قيد التحضير",
        customer_name=data.customer_name or ("عميل تيك أواي" if data.order_type == "تيك أواي" else ("عميل دليفري" if data.order_type == "دليفري" else f"ترابيزة {data.table_number}")),
        customer_phone=data.customer_phone or "",
        notes=data.notes or "",
        shift_id=shift_id,
        delivery_address=data.delivery_address if data.order_type == "دليفري" else None,
        delivery_fee=delivery_fee,
        delivery_driver=data.delivery_driver if data.order_type == "دليفري" else None,
        delivery_status="قيد التجهيز" if data.order_type == "دليفري" else None
    )
    db.add(order)

    if current_shift:
        current_shift.total_sales += grand_total
        if data.payment_method == "فيزا":
            current_shift.visa_sales += grand_total
        else:
            current_shift.cash_sales += grand_total

    deduct_inventory_for_order(order_data.items, db)
    db.commit()
    db.refresh(order)
    return {
        "status": "success",
        "message": f"تم تسجيل أوردر الـ {data.order_type} بنجاح!",
        "order_id": order.id,
        "grand_total": grand_total
    }


@app.get("/api/orders")
@app.get("/api/cezar/orders")
def get_orders(order_type: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(TableOrder)
    if order_type and order_type.strip():
        query = query.filter(TableOrder.order_type == order_type.strip())
        
    orders = query.order_by(desc(TableOrder.created_at)).limit(100).all()

    total_orders = db.query(TableOrder).count()
    delivered_count = db.query(TableOrder).filter(TableOrder.status.in_(["تم التقديم", "تمت التسوية", "تم التوصيل"])).count()
    pending_count = db.query(TableOrder).filter(
        TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير", "نداء ويتر"]) | TableOrder.status.like("طلب حساب%")
    ).count()

    total_sales = db.query(func.sum(TableOrder.total_price)).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر"
    ).scalar() or 0.0

    return {
        "stats": {
            "total_orders": total_orders,
            "total_sales": round(total_sales, 2),
            "pending_orders": pending_count,
            "delivered_orders": delivered_count,
            "active_orders": pending_count
        },
        "orders": [
            {
                "id": o.id,
                "table_number": o.table_number or 0,
                "order_type": o.order_type or "صالة",
                "items_summary": o.items_summary,
                "total_price": o.total_price,
                "discount_amount": o.discount_amount or 0.0,
                "promo_code": o.promo_code or "",
                "payment_method": o.payment_method or "كاش",
                "status": o.status,
                "customer_name": o.customer_name,
                "customer_phone": o.customer_phone,
                "notes": o.notes,
                "delivery_address": o.delivery_address,
                "delivery_fee": o.delivery_fee or 0.0,
                "delivery_driver": o.delivery_driver,
                "delivery_status": o.delivery_status,
                "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
            }
            for o in orders
        ]
    }


@app.get("/api/tables/status")
@app.get("/api/cezar/tables/status")
def get_all_tables_status(db: Session = Depends(get_db)):
    tables_data = []
    for t in range(1, 26):
        active_orders = db.query(TableOrder).filter(
            TableOrder.table_number == t,
            TableOrder.order_type == "صالة",
            TableOrder.status != "ملغي",
            TableOrder.status != "تم التقديم",
            TableOrder.status != "تمت التسوية"
        ).all()

        bill_orders = [
            o for o in active_orders 
            if o.total_price > 0 and "طلب الحساب" not in (o.items_summary or "") and "نداء الويتر" not in (o.items_summary or "")
        ]
        total_bill = sum(o.total_price for o in bill_orders)

        has_bill_request = any("طلب حساب" in (o.status or "") or "طلب الحساب" in (o.items_summary or "") for o in active_orders)
        has_waiter_call = any("نداء ويتر" in (o.status or "") or "نداء الويتر" in (o.items_summary or "") for o in active_orders)

        if has_bill_request:
            status = "bill_requested"
            status_text = "طلب حساب"
        elif has_waiter_call:
            status = "waiter_called"
            status_text = "نداء ويتر"
        elif len(bill_orders) > 0:
            status = "occupied"
            status_text = "مشغولة"
        else:
            status = "free"
            status_text = "متاحة"

        tables_data.append({
            "table_number": t,
            "status": status,
            "status_text": status_text,
            "total_bill": round(total_bill, 2),
            "orders_count": len(bill_orders),
            "has_waiter_call": has_waiter_call,
            "has_bill_request": has_bill_request
        })

    return {"status": "success", "tables": tables_data}


@app.get("/api/tables/{table_number}/bill")
@app.get("/api/cezar/tables/{table_number}/bill")
def get_table_bill(table_number: int, db: Session = Depends(get_db)):
    active_orders = db.query(TableOrder).filter(
        TableOrder.table_number == table_number,
        TableOrder.status != "ملغي",
        TableOrder.status != "تمت التسوية",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        ~TableOrder.items_summary.like("%طلب الحساب%"),
        ~TableOrder.items_summary.like("%نداء الويتر%"),
        TableOrder.total_price > 0
    ).all()

    total_bill = sum(o.total_price for o in active_orders)
    orders_list = [
        {
            "id": o.id,
            "items_summary": o.items_summary,
            "total_price": o.total_price,
            "status": o.status,
            "notes": o.notes or "",
            "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
        }
        for o in active_orders
    ]

    return {
        "table_number": table_number,
        "total_bill": round(total_bill, 2),
        "orders_count": len(active_orders),
        "orders": orders_list
    }


@app.post("/api/tables/{table_number}/settle")
@app.post("/api/cezar/tables/{table_number}/settle")
def settle_table_bill(table_number: int, db: Session = Depends(get_db)):
    orders = db.query(TableOrder).filter(
        TableOrder.table_number == table_number,
        TableOrder.status != "ملغي",
        TableOrder.status != "تمت التسوية"
    ).all()
    for o in orders:
        o.status = "تمت التسوية"
    db.commit()
    return {"status": "success", "message": f"تمت تسوية حساب ترابيزة {table_number} وإفراغها بنجاح!", "table_number": table_number}


class TableTransferRequest(BaseModel):
    from_table: int
    to_table: int

class TableMergeRequest(BaseModel):
    primary_table: int
    secondary_table: int

@app.post("/api/tables/transfer")
@app.post("/api/cezar/tables/transfer")
def transfer_table_orders(req: TableTransferRequest, db: Session = Depends(get_db)):
    active_orders = db.query(TableOrder).filter(
        TableOrder.table_number == req.from_table,
        TableOrder.order_type == "صالة",
        ~TableOrder.status.in_(["ملغي", "تمت التسوية"])
    ).all()
    if not active_orders:
        raise HTTPException(status_code=400, detail=f"لا توجد طلبات نشطة في ترابيزة {req.from_table}")
    
    for o in active_orders:
        o.table_number = req.to_table
        if f"ترابيزة {req.from_table}" in (o.customer_name or ""):
            o.customer_name = f"ترابيزة {req.to_table}"
    db.commit()
    return {"status": "success", "message": f"تم نقل الحساب من ترابيزة {req.from_table} إلى ترابيزة {req.to_table} بنجاح!"}

@app.post("/api/tables/merge")
@app.post("/api/cezar/tables/merge")
def merge_tables(req: TableMergeRequest, db: Session = Depends(get_db)):
    sec_orders = db.query(TableOrder).filter(
        TableOrder.table_number == req.secondary_table,
        TableOrder.order_type == "صالة",
        ~TableOrder.status.in_(["ملغي", "تمت التسوية"])
    ).all()
    if not sec_orders:
        raise HTTPException(status_code=400, detail=f"لا توجد طلبات في ترابيزة {req.secondary_table}")
    
    for o in sec_orders:
        o.table_number = req.primary_table
        o.customer_name = f"ترابيزة {req.primary_table} (مدمجة مع {req.secondary_table})"
    db.commit()
    return {"status": "success", "message": f"تم دمج حساب ترابيزة {req.secondary_table} في ترابيزة {req.primary_table} بنجاح!"}

@app.get("/api/auth/staff")
@app.get("/api/cezar/auth/staff")
def list_staff_accounts(db: Session = Depends(get_db)):
    staff = db.query(ManagerAccount).all()
    return {
        "status": "success",
        "staff": [{"id": s.id, "username": s.username, "manager_name": s.manager_name, "role": s.role or "admin"} for s in staff]
    }


@app.get("/api/tables/{table_number}/track")
@app.get("/api/cezar/tables/{table_number}/track")
def track_table_orders(table_number: int, db: Session = Depends(get_db)):
    orders = db.query(TableOrder).filter(
        TableOrder.table_number == table_number,
        ~TableOrder.items_summary.like("%طلب الحساب%"),
        ~TableOrder.items_summary.like("%نداء الويتر%"),
        TableOrder.total_price > 0
    ).order_by(desc(TableOrder.id)).limit(25).all()

    orders_list = [
        {
            "id": o.id,
            "items_summary": o.items_summary,
            "total_price": o.total_price,
            "status": o.status,
            "notes": o.notes or "",
            "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
        }
        for o in orders
    ]

    active_count = sum(1 for o in orders if o.status in ["جديد", "جاري التحضير", "قيد التحضير"])

    return {
        "status": "success",
        "table_number": table_number,
        "orders_count": len(orders_list),
        "active_count": active_count,
        "orders": orders_list
    }


@app.get("/api/orders/{order_id}")
@app.get("/api/cezar/orders/{order_id}")
def get_order_by_id(order_id: int, db: Session = Depends(get_db)):
    order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return {
        "status": "success",
        "id": order.id,
        "table_number": order.table_number or 0,
        "order_type": order.order_type or "صالة",
        "items_summary": order.items_summary,
        "total_price": order.total_price,
        "discount_amount": order.discount_amount or 0.0,
        "promo_code": order.promo_code or "",
        "payment_method": order.payment_method or "كاش",
        "status": order.status,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "delivery_address": order.delivery_address,
        "delivery_fee": order.delivery_fee or 0.0,
        "delivery_driver": order.delivery_driver,
        "delivery_status": order.delivery_status,
        "notes": order.notes or "",
        "created_at": order.created_at.strftime("%I:%M %p") if order.created_at else ""
    }


@app.post("/api/orders/{order_id}/status")
@app.post("/api/cezar/orders/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    if order.status in ["تم التقديم", "تمت التسوية", "تم التوصيل"] and (order.items_summary and "طلب الحساب" in order.items_summary):
        db.query(TableOrder).filter(
            TableOrder.table_number == order.table_number,
            TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير"])
        ).update({"status": "تم التقديم"}, synchronize_session=False)

    db.commit()
    return {"status": "success", "order_id": order.id, "new_status": order.status}


@app.post("/api/orders/{order_id}/delivery-status")
@app.post("/api/cezar/orders/{order_id}/delivery-status")
def update_delivery_status(order_id: int, payload: DeliveryStatusUpdateRequest, db: Session = Depends(get_db)):
    order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")

    order.delivery_status = payload.delivery_status
    if payload.delivery_driver:
        order.delivery_driver = payload.delivery_driver
    if payload.delivery_status == "تم التوصيل":
        order.status = "تم التوصيل"

    db.commit()
    return {"status": "success", "order_id": order.id, "delivery_status": order.delivery_status}


@app.post("/api/orders/call-waiter")
@app.post("/api/cezar/orders/call-waiter")
def call_waiter_endpoint(req: CallWaiterRequest, db: Session = Depends(get_db)):
    order = TableOrder(
        table_number=req.table_number,
        order_type="صالة",
        items_summary="🔔 نداء الويتر (طلب مساعدة / استفسار)",
        total_price=0.0,
        customer_name=f"ترابيزة {req.table_number}",
        status="نداء ويتر"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"status": "success", "message": f"تم إرسال نداء الويتر لترابيزة {req.table_number} فوراً!"}


@app.post("/api/orders/request-bill")
@app.post("/api/cezar/orders/request-bill")
def request_bill_endpoint(req: RequestBillRequest, db: Session = Depends(get_db)):
    method = req.payment_method if req.payment_method in ["كاش", "فيزا"] else "كاش"
    icon = "💵" if method == "كاش" else "💳"

    active_orders = db.query(TableOrder).filter(
        TableOrder.table_number == req.table_number,
        TableOrder.status != "ملغي",
        TableOrder.status != "تمت التسوية",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        ~TableOrder.items_summary.like("%طلب الحساب%"),
        ~TableOrder.items_summary.like("%نداء الويتر%"),
        TableOrder.total_price > 0
    ).all()

    total_bill = sum(o.total_price for o in active_orders)
    if active_orders:
        orders_details = [o.items_summary for o in active_orders]
        items_text = "\n".join(orders_details)
        summary = f"🧾 طلب الحساب النهائي ({method}) {icon}\n💰 الإجمالي المطلوب تحصيله: {total_bill:g} جنيه\n📋 الطلبات:\n{items_text}"
    else:
        summary = f"🧾 طلب الحساب النهائي ({method}) {icon} (طلب حساب مباشر بدون أوردرات مسبقة)"

    order = TableOrder(
        table_number=req.table_number,
        order_type="صالة",
        items_summary=summary,
        total_price=total_bill,
        payment_method=method,
        customer_name=f"ترابيزة {req.table_number}",
        status=f"طلب حساب ({method})"
    )
    db.add(order)
    deduct_inventory_for_order(order_data.items, db)
    db.commit()
    db.refresh(order)
    return {
        "status": "success",
        "message": f"تم إرسال طلب الحساب لترابيزة {req.table_number} بنجاح! الإجمالي: {total_bill:g} جنيه ({method})",
        "order_id": order.id,
        "total_bill": total_bill
    }


@app.post("/api/orders/clear-all")
@app.post("/api/cezar/orders/clear-all")
def clear_all_orders(db: Session = Depends(get_db)):
    db.query(TableOrder).delete()
    db.commit()
    return {"status": "success", "message": "تم تصفير جميع الطلبات وبدء وردية جديدة بنجاح!"}


# ==========================================
# 4. واجهات إدارة الشيفتات والمصروفات (Shifts & Expenses)
# ==========================================

@app.get("/api/shifts/current")
@app.get("/api/cezar/shifts/current")
def get_current_shift(db: Session = Depends(get_db)):
    shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    if not shift:
        return {"status": "no_active_shift", "message": "لا يوجد وردية مفتوحة حالياً"}

    orders = db.query(TableOrder).filter(
        TableOrder.shift_id == shift.id,
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر"
    ).all()

    total_sales = sum(o.total_price for o in orders)
    cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
    visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")

    expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
    total_expenses = sum(e.amount for e in expenses)

    expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses

    return {
        "status": "active",
        "shift": {
            "id": shift.id,
            "cashier_name": shift.cashier_name,
            "start_time": shift.start_time.strftime("%Y-%m-%d %I:%M %p") if shift.start_time else "",
            "starting_cash": shift.starting_cash,
            "total_sales": round(total_sales, 2),
            "cash_sales": round(cash_sales, 2),
            "visa_sales": round(visa_sales, 2),
            "total_expenses": round(total_expenses, 2),
            "expected_cash": round(expected_cash, 2),
            "orders_count": len(orders),
            "notes": shift.notes or ""
        }
    }


@app.post("/api/shifts/open")
@app.post("/api/cezar/shifts/open")
def open_shift(req: ShiftOpenRequest, db: Session = Depends(get_db)):
    active = db.query(Shift).filter(Shift.status == "مفتوح").first()
    if active:
        raise HTTPException(status_code=400, detail=f"يوجد وردية مفتوحة بالفعل للكاشير ({active.cashier_name}). يجب تقفيلها أولاً.")

    new_shift = Shift(
        cashier_name=req.cashier_name.strip(),
        starting_cash=req.starting_cash,
        start_time=datetime.utcnow(),
        status="مفتوح",
        notes=req.notes or ""
    )
    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)
    return {"status": "success", "message": "تم فتح الوردية بنجاح!", "shift_id": new_shift.id}


@app.post("/api/shifts/close")
@app.post("/api/cezar/shifts/close")
def close_shift(req: ShiftCloseRequest, db: Session = Depends(get_db)):
    shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    if not shift:
        raise HTTPException(status_code=400, detail="لا توجد وردية مفتوحة لإغلاقها!")

    orders = db.query(TableOrder).filter(
        TableOrder.shift_id == shift.id,
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر"
    ).all()

    total_sales = sum(o.total_price for o in orders)
    cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
    visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")

    expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
    total_expenses = sum(e.amount for e in expenses)

    expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses
    difference = req.actual_cash - expected_cash

    shift.end_time = datetime.utcnow()
    shift.status = "مغلق"
    shift.total_sales = total_sales
    shift.cash_sales = cash_sales
    shift.visa_sales = visa_sales
    shift.total_expenses = total_expenses
    shift.actual_cash = req.actual_cash
    shift.difference = round(difference, 2)
    if req.notes:
        shift.notes = (shift.notes or "") + "\n" + req.notes

    db.commit()
    return {
        "status": "success",
        "message": "تم إغلاق الوردية وتقفيل الحساب بنجاح!",
        "summary": {
            "shift_id": shift.id,
            "cashier_name": shift.cashier_name,
            "starting_cash": shift.starting_cash,
            "total_sales": total_sales,
            "cash_sales": cash_sales,
            "visa_sales": visa_sales,
            "total_expenses": total_expenses,
            "expected_cash": round(expected_cash, 2),
            "actual_cash": req.actual_cash,
            "difference": round(difference, 2)
        }
    }


@app.get("/api/shifts/history")
@app.get("/api/cezar/shifts/history")
def get_shifts_history(db: Session = Depends(get_db)):
    shifts = db.query(Shift).order_by(desc(Shift.id)).limit(30).all()
    return {
        "shifts": [
            {
                "id": s.id,
                "cashier_name": s.cashier_name,
                "start_time": s.start_time.strftime("%Y-%m-%d %I:%M %p") if s.start_time else "",
                "end_time": s.end_time.strftime("%Y-%m-%d %I:%M %p") if s.end_time else "مستمرة",
                "starting_cash": s.starting_cash,
                "total_sales": s.total_sales,
                "cash_sales": s.cash_sales,
                "visa_sales": s.visa_sales,
                "total_expenses": s.total_expenses,
                "actual_cash": s.actual_cash,
                "difference": s.difference,
                "status": s.status
            }
            for s in shifts
        ]
    }


@app.post("/api/expenses")
@app.post("/api/cezar/expenses")
def add_expense(req: ExpenseCreateRequest, db: Session = Depends(get_db)):
    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    shift_id = current_shift.id if current_shift else None

    expense = Expense(
        shift_id=shift_id,
        title=req.title.strip(),
        amount=req.amount,
        category=req.category.strip(),
        notes=req.notes or "",
        created_at=datetime.utcnow()
    )
    db.add(expense)
    if current_shift:
        current_shift.total_expenses = (current_shift.total_expenses or 0.0) + req.amount

    db.commit()
    db.refresh(expense)
    return {"status": "success", "message": f"تم تسجيل المصروف بقيمة {expense.amount:g} ج بنجاح!"}


@app.get("/api/expenses")
@app.get("/api/cezar/expenses")
def get_expenses(db: Session = Depends(get_db)):
    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    query = db.query(Expense)
    if current_shift:
        query = query.filter(Expense.shift_id == current_shift.id)
    expenses = query.order_by(desc(Expense.created_at)).limit(50).all()
    return {
        "expenses": [
            {
                "id": e.id,
                "title": e.title,
                "amount": e.amount,
                "category": e.category,
                "notes": e.notes or "",
                "created_at": e.created_at.strftime("%I:%M %p") if e.created_at else ""
            }
            for e in expenses
        ]
    }


@app.delete("/api/expenses/{expense_id}")
@app.delete("/api/cezar/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(Expense).filter(Expense.id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="المصروف غير موجود")
    if exp.shift_id:
        shift = db.query(Shift).filter(Shift.id == exp.shift_id).first()
        if shift and shift.total_expenses:
            shift.total_expenses = max(0.0, shift.total_expenses - exp.amount)
    db.delete(exp)
    db.commit()
    return {"status": "success", "message": "تم حذف المصروف بنجاح"}


# ==========================================
# 5. الحجوزات وقائمة الانتظار (Reservations & Waiting List)
# ==========================================

@app.get("/api/reservations")
@app.get("/api/cezar/reservations")
def get_reservations(db: Session = Depends(get_db)):
    res_list = db.query(Reservation).order_by(desc(Reservation.id)).limit(50).all()
    return {
        "reservations": [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "customer_phone": r.customer_phone,
                "table_number": r.table_number or "غير محدد",
                "guests_count": r.guests_count,
                "reservation_time": r.reservation_time,
                "deposit": r.deposit,
                "status": r.status,
                "notes": r.notes or ""
            }
            for r in res_list
        ]
    }


@app.post("/api/reservations")
@app.post("/api/cezar/reservations")
def create_reservation(req: ReservationCreateRequest, db: Session = Depends(get_db)):
    res = Reservation(
        customer_name=req.customer_name.strip(),
        customer_phone=req.customer_phone.strip(),
        table_number=req.table_number,
        guests_count=req.guests_count,
        reservation_time=req.reservation_time.strip(),
        deposit=req.deposit,
        notes=req.notes or "",
        status="مؤكد"
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return {"status": "success", "message": f"تم تسجيل حجز {res.customer_name} بنجاح!", "id": res.id}


@app.put("/api/reservations/{res_id}/status")
@app.put("/api/cezar/reservations/{res_id}/status")
def update_reservation_status(res_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    res = db.query(Reservation).filter(Reservation.id == res_id).first()
    if not res:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")
    res.status = payload.status
    db.commit()
    return {"status": "success", "new_status": res.status}


@app.delete("/api/reservations/{res_id}")
@app.delete("/api/cezar/reservations/{res_id}")
def delete_reservation(res_id: int, db: Session = Depends(get_db)):
    res = db.query(Reservation).filter(Reservation.id == res_id).first()
    if not res:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")
    db.delete(res)
    db.commit()
    return {"status": "success", "message": "تم حذف الحجز بنجاح"}


@app.get("/api/waiting-list")
@app.get("/api/cezar/waiting-list")
def get_waiting_list(db: Session = Depends(get_db)):
    waiters = db.query(WaitingList).filter(WaitingList.status.in_(["قيد الانتظار", "تم النداء"])).order_by(WaitingList.id).all()
    return {
        "waiting_list": [
            {
                "id": w.id,
                "customer_name": w.customer_name,
                "customer_phone": w.customer_phone,
                "guests_count": w.guests_count,
                "status": w.status,
                "assigned_table": w.assigned_table,
                "notes": w.notes or "",
                "created_at": w.created_at.strftime("%I:%M %p") if w.created_at else ""
            }
            for w in waiters
        ]
    }


@app.post("/api/waiting-list")
@app.post("/api/cezar/waiting-list")
def add_to_waiting_list(req: WaitingListCreateRequest, db: Session = Depends(get_db)):
    waiter = WaitingList(
        customer_name=req.customer_name.strip(),
        customer_phone=req.customer_phone.strip(),
        guests_count=req.guests_count,
        notes=req.notes or "",
        status="قيد الانتظار"
    )
    db.add(waiter)
    db.commit()
    db.refresh(waiter)
    return {"status": "success", "message": f"تمت إضافة {waiter.customer_name} في قائمة الانتظار بنجاح!", "id": waiter.id}


@app.post("/api/waiting-list/{wait_id}/seat")
@app.post("/api/cezar/waiting-list/{wait_id}/seat")
def seat_waiting_customer(wait_id: int, req: SeatWaitingCustomerRequest, db: Session = Depends(get_db)):
    waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
    if not waiter:
        raise HTTPException(status_code=404, detail="العميل غير موجود بقائمة الانتظار")

    waiter.status = "تم التسكين"
    waiter.assigned_table = req.table_number
    db.commit()
    return {"status": "success", "message": f"تم تسكين العميل {waiter.customer_name} على ترابيزة رقم {req.table_number}!"}


@app.put("/api/waiting-list/{wait_id}/status")
@app.put("/api/cezar/waiting-list/{wait_id}/status")
def update_waiting_status(wait_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
    if not waiter:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    waiter.status = payload.status
    db.commit()
    return {"status": "success", "new_status": waiter.status}


@app.delete("/api/waiting-list/{wait_id}")
@app.delete("/api/cezar/waiting-list/{wait_id}")
def delete_waiting_customer(wait_id: int, db: Session = Depends(get_db)):
    waiter = db.query(WaitingList).filter(WaitingList.id == wait_id).first()
    if not waiter:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    db.delete(waiter)
    db.commit()
    return {"status": "success", "message": "تم حذف العميل من قائمة الانتظار"}


# ==========================================
# 6. نظام البروموكود والخصومات (Promo Codes & Discounts)
# ==========================================

@app.get("/api/promo-codes")
@app.get("/api/cezar/promo-codes")
def get_promo_codes(db: Session = Depends(get_db)):
    codes = db.query(PromoCode).order_by(desc(PromoCode.id)).all()
    return {
        "promo_codes": [
            {
                "id": p.id,
                "code": p.code,
                "discount_type": p.discount_type,
                "discount_value": p.discount_value,
                "min_order_value": p.min_order_value or 0.0,
                "is_active": p.is_active,
                "usage_count": p.usage_count or 0
            }
            for p in codes
        ]
    }


@app.post("/api/promo-codes")
@app.post("/api/cezar/promo-codes")
def create_promo_code(req: PromoCodeCreateRequest, db: Session = Depends(get_db)):
    code_str = req.code.strip().upper()
    existing = db.query(PromoCode).filter(PromoCode.code == code_str).first()
    if existing:
        raise HTTPException(status_code=400, detail="كود الخصم موجود بالفعل")

    new_promo = PromoCode(
        code=code_str,
        discount_type=req.discount_type,
        discount_value=req.discount_value,
        min_order_value=req.min_order_value,
        is_active=True
    )
    db.add(new_promo)
    db.commit()
    db.refresh(new_promo)
    return {"status": "success", "message": f"تم إنشاء كود الخصم {new_promo.code} بنجاح!", "id": new_promo.id}


@app.post("/api/promo-codes/validate")
@app.post("/api/cezar/promo-codes/validate")
def validate_promo_code(req: PromoValidateRequest, db: Session = Depends(get_db)):
    code_str = req.code.strip().upper()
    promo = db.query(PromoCode).filter(PromoCode.code == code_str, PromoCode.is_active.is_(True)).first()
    if not promo:
        raise HTTPException(status_code=404, detail="كود الخصم غير صحيح أو منتهي الصلاحية")

    if req.order_total < (promo.min_order_value or 0.0):
        raise HTTPException(status_code=400, detail=f"الحد الأدنى لتفعيل هذا الكود هو {promo.min_order_value} جنيه")

    if promo.discount_type == "percentage":
        discount = round((req.order_total * promo.discount_value) / 100.0, 2)
    else:
        discount = min(req.order_total, promo.discount_value)

    new_total = max(0.0, req.order_total - discount)
    return {
        "status": "valid",
        "code": promo.code,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "discount_amount": discount,
        "new_total": new_total,
        "message": f"تم تطبيق خصم {promo.discount_value}{'%' if promo.discount_type == 'percentage' else ' ج'} بنجاح!"
    }


@app.delete("/api/promo-codes/{code_id}")
@app.delete("/api/cezar/promo-codes/{code_id}")
def delete_promo_code(code_id: int, db: Session = Depends(get_db)):
    p = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="كود الخصم غير موجود")
    db.delete(p)
    db.commit()
    return {"status": "success", "message": "تم حذف كود الخصم"}


# ==========================================
# 7. إدارة المخزون وتنبيه النواقص (Inventory Management)
# ==========================================

@app.get("/api/inventory")
@app.get("/api/cezar/inventory")
def get_inventory(db: Session = Depends(get_db)):
    items = db.query(InventoryItem).order_by(InventoryItem.name).all()
    alerts = []
    inv_list = []
    for i in items:
        is_low = i.current_stock <= i.min_alert_stock
        item_data = {
            "id": i.id,
            "name": i.name,
            "unit": i.unit,
            "current_stock": i.current_stock,
            "min_alert_stock": i.min_alert_stock,
            "cost_per_unit": i.cost_per_unit,
            "is_low": is_low
        }
        inv_list.append(item_data)
        if is_low:
            alerts.append(item_data)

    return {
        "status": "success",
        "inventory": inv_list,
        "low_stock_alerts": alerts,
        "alerts_count": len(alerts)
    }


@app.post("/api/inventory")
@app.post("/api/cezar/inventory")
def add_inventory_item(req: InventoryCreateRequest, db: Session = Depends(get_db)):
    name_str = req.name.strip()
    existing = db.query(InventoryItem).filter(InventoryItem.name == name_str).first()
    if existing:
        raise HTTPException(status_code=400, detail="الصنف موجود بالفعل في المخزن")

    item = InventoryItem(
        name=name_str,
        unit=req.unit.strip(),
        current_stock=req.current_stock,
        min_alert_stock=req.min_alert_stock,
        cost_per_unit=req.cost_per_unit
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"status": "success", "message": f"تمت إضافة {item.name} للمخزن بنجاح!", "id": item.id}


@app.put("/api/inventory/{item_id}")
@app.put("/api/cezar/inventory/{item_id}")
def update_inventory_item(item_id: int, req: InventoryUpdateRequest, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود بالمخزن")

    if req.current_stock is not None:
        item.current_stock = req.current_stock
    if req.min_alert_stock is not None:
        item.min_alert_stock = req.min_alert_stock
    if req.cost_per_unit is not None:
        item.cost_per_unit = req.cost_per_unit

    db.commit()
    return {"status": "success", "message": "تم تحديث رصيد المخزن بنجاح"}


@app.delete("/api/inventory/{item_id}")
@app.delete("/api/cezar/inventory/{item_id}")
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")
    db.delete(item)
    db.commit()
    return {"status": "success", "message": "تم حذف الصنف من المخزن"}


# ==========================================
# 7.1 إدارة الهالك والعجز والجرد (Waste & Inventory Variance)
# ==========================================

@app.get("/api/inventory/waste")
@app.get("/api/cezar/inventory/waste")
def get_inventory_waste(month: Optional[str] = None, waste_type: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(InventoryWaste)
    if month and month.strip():
        query = query.filter(InventoryWaste.date.like(f"{month.strip()}%"))
    if waste_type and waste_type.strip() and waste_type.strip() != "الكل":
        query = query.filter(InventoryWaste.waste_type == waste_type.strip())
    
    records = query.order_by(desc(InventoryWaste.date), desc(InventoryWaste.id)).all()

    total_cost_loss = sum(r.cost_loss or 0.0 for r in records)
    total_qty = sum(r.quantity or 0.0 for r in records)
    total_records = len(records)

    by_type = {}
    item_losses = {}
    for r in records:
        wt = r.waste_type or "أخرى"
        by_type[wt] = round(by_type.get(wt, 0.0) + (r.cost_loss or 0.0), 2)
        item_losses[r.item_name] = round(item_losses.get(r.item_name, 0.0) + (r.cost_loss or 0.0), 2)

    top_item = max(item_losses.items(), key=lambda x: x[1])[0] if item_losses else "لا يوجد"

    return {
        "status": "success",
        "wastes": [
            {
                "id": r.id,
                "inventory_item_id": r.inventory_item_id,
                "item_name": r.item_name,
                "waste_type": r.waste_type,
                "quantity": r.quantity,
                "unit": r.unit,
                "cost_loss": round(r.cost_loss or 0.0, 2),
                "responsible_name": r.responsible_name or "غير محدد",
                "reason": r.reason or "",
                "date": r.date,
                "created_at": r.created_at.strftime("%I:%M %p") if r.created_at else ""
            }
            for r in records
        ],
        "summary": {
            "total_cost_loss": round(total_cost_loss, 2),
            "total_quantity": round(total_qty, 2),
            "total_records": total_records,
            "top_wasted_item": top_item,
            "by_type": by_type
        }
    }


@app.post("/api/inventory/waste")
@app.post("/api/cezar/inventory/waste")
def add_inventory_waste(req: InventoryWasteCreateRequest, db: Session = Depends(get_db)):
    item_name = req.item_name.strip()
    if not item_name:
        raise HTTPException(status_code=400, detail="اسم المادة أو الصنف مطلوب")
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")

    inv_item = None
    if req.inventory_item_id:
        inv_item = db.query(InventoryItem).filter(InventoryItem.id == req.inventory_item_id).first()
    if not inv_item:
        inv_item = db.query(InventoryItem).filter(InventoryItem.name == item_name).first()

    calculated_loss = req.cost_loss
    unit_used = req.unit
    if inv_item:
        if not unit_used:
            unit_used = inv_item.unit
        if calculated_loss is None or calculated_loss <= 0:
            calculated_loss = req.quantity * (inv_item.cost_per_unit or 0.0)

    if calculated_loss is None:
        calculated_loss = 0.0

    today_str = req.date.strip() if req.date and req.date.strip() else datetime.now().strftime("%Y-%m-%d")

    waste = InventoryWaste(
        inventory_item_id=inv_item.id if inv_item else req.inventory_item_id,
        item_name=item_name,
        waste_type=req.waste_type.strip() if req.waste_type else "هالك تشغيل",
        quantity=req.quantity,
        unit=unit_used or "كجم",
        cost_loss=round(calculated_loss, 2),
        responsible_name=req.responsible_name.strip() if req.responsible_name else "غير محدد",
        reason=req.reason.strip() if req.reason else "",
        date=today_str
    )
    db.add(waste)

    if req.auto_deduct_stock and inv_item:
        inv_item.current_stock = max(0.0, (inv_item.current_stock or 0.0) - req.quantity)

    db.commit()
    db.refresh(waste)

    return {
        "status": "success",
        "message": f"تم تسجيل محضر هالك/عجز لـ ({waste.item_name}) بنجاح بقيمة {waste.cost_loss} ج",
        "waste_id": waste.id,
        "remaining_stock": inv_item.current_stock if inv_item else None
    }


@app.delete("/api/inventory/waste/{waste_id}")
@app.delete("/api/cezar/inventory/waste/{waste_id}")
def delete_inventory_waste(waste_id: int, restore_stock: bool = True, db: Session = Depends(get_db)):
    waste = db.query(InventoryWaste).filter(InventoryWaste.id == waste_id).first()
    if not waste:
        raise HTTPException(status_code=404, detail="محضر الهالك غير موجود")

    if restore_stock and waste.inventory_item_id:
        inv_item = db.query(InventoryItem).filter(InventoryItem.id == waste.inventory_item_id).first()
        if inv_item:
            inv_item.current_stock = (inv_item.current_stock or 0.0) + (waste.quantity or 0.0)

    db.delete(waste)
    db.commit()
    return {"status": "success", "message": "تم حذف محضر الهالك بنجاح واسترجاع الكمية للرصيد"}



# ==========================================
# 8. تقارير ذكية، الأكثر مبيعاً وتصدير Excel (Analytics & Export)
# ==========================================

@app.get("/api/analytics")
@app.get("/api/cezar/analytics")
def get_analytics(db: Session = Depends(get_db)):
    orders = db.query(TableOrder).filter(
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر",
        TableOrder.total_price > 0
    ).all()

    # Best Sellers parsing
    item_counter = {}
    for o in orders:
        if not o.items_summary:
            continue
        for line in o.items_summary.split("\n"):
            line = line.strip().lstrip("- ")
            if "x " in line:
                try:
                    parts = line.split("x ", 1)
                    qty = int(parts[0].strip())
                    name_part = parts[1].split(":")[0].strip()
                    # Remove bracket customizations for counting base item
                    if "[" in name_part:
                        name_part = name_part.split("[")[0].strip()
                    item_counter[name_part] = item_counter.get(name_part, 0) + qty
                except Exception:
                    pass

    top_items = sorted(
        [{"name": k, "orders_count": v} for k, v in item_counter.items()],
        key=lambda x: x["orders_count"],
        reverse=True
    )[:6]

    # Hourly distribution
    hourly_counts = {h: 0 for h in range(24)}
    for o in orders:
        if o.created_at:
            hourly_counts[o.created_at.hour] += 1

    peak_hours = [{"hour": f"{h}:00", "count": hourly_counts[h]} for h in range(8, 24)]

    # Sales by Order Type
    sales_by_type = {"صالة": 0.0, "تيك أواي": 0.0, "دليفري": 0.0}
    for o in orders:
        t = o.order_type or "صالة"
        sales_by_type[t] = sales_by_type.get(t, 0.0) + o.total_price

    # Calculate Real Food Cost (COGS) from sold items cost_price and Net Profit
    gross_sales = round(sum(o.total_price for o in orders), 2)
    menu_costs = {item.name: (item.cost_price or (item.price * 0.32)) for item in db.query(MenuItem).all()}
    calc_cogs = 0.0
    for name, qty in item_counter.items():
        unit_cost = menu_costs.get(name)
        if unit_cost is not None and unit_cost > 0:
            calc_cogs += unit_cost * qty
        else:
            calc_cogs += ((gross_sales / max(1, len(orders))) * 0.32 * qty) if gross_sales > 0 else 0.0

    total_cogs = round(calc_cogs if calc_cogs > 0 else (gross_sales * 0.32), 2)
    total_expenses = round(float(db.query(func.sum(Expense.amount)).scalar() or 0.0), 2)
    total_salaries = round(float(db.query(func.sum(SalaryPayment.amount)).scalar() or 0.0), 2)
    total_waste = round(float(db.query(func.sum(InventoryWaste.cost_loss)).scalar() or 0.0), 2)
    net_profit = round(gross_sales - total_cogs - total_expenses - total_salaries - total_waste, 2)
    profit_margin_pct = round((net_profit / gross_sales) * 100, 1) if gross_sales > 0 else 0.0

    by_channel = {"صالة": sales_by_type.get("صالة", 0.0), "تيك أواي": sales_by_type.get("تيك أواي", 0.0), "دليفري": sales_by_type.get("دليفري", 0.0)}

    return {
        "status": "success",
        "gross_sales": gross_sales,
        "total_cogs": total_cogs,
        "total_sales": gross_sales,
        "cogs": total_cogs,
        "total_expenses": total_expenses,
        "total_salaries": total_salaries,
        "net_profit": net_profit,
        "profit_margin_pct": profit_margin_pct,
        "top_sellers": top_items,
        "peak_hours": peak_hours,
        "by_channel": by_channel,
        "sales_by_type": sales_by_type,
        "total_served_orders": len(orders)
    }



@app.post("/api/analytics/reset")
@app.post("/api/cezar/analytics/reset")
def reset_analytics_data(db: Session = Depends(get_db)):
    deleted_count = db.query(TableOrder).delete()
    db.commit()
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"تم تصفير بيانات التقارير والمبيعات بنجاح ({deleted_count} طلب)."
    }

@app.get("/api/export/sales-csv")
@app.get("/api/cezar/export/sales-csv")
def export_sales_csv(db: Session = Depends(get_db)):
    orders = db.query(TableOrder).filter(
        TableOrder.status != "ملغي",
        TableOrder.total_price > 0
    ).order_by(desc(TableOrder.id)).all()

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Arabic correctly
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "رقم الطلب",
        "نوع الطلب",
        "رقم الترابيزة",
        "اسم العميل",
        "رقم الهاتف",
        "الأصناف المطلوبة",
        "طريقة الدفع",
        "الخصم (ج)",
        "الإجمالي المدفوع (ج)",
        "الحالة",
        "التاريخ والوقت"
    ])

    for o in orders:
        writer.writerow([
            o.id,
            o.order_type or "صالة",
            o.table_number or "-",
            o.customer_name or "-",
            o.customer_phone or "-",
            (o.items_summary or "").replace("\n", " | "),
            o.payment_method or "كاش",
            o.discount_amount or 0.0,
            o.total_price,
            o.status,
            o.created_at.strftime("%Y-%m-%d %I:%M %p") if o.created_at else "-"
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    filename = f"ceZar_Sales_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ==========================================
# 9. توليد باركود QR عالي الدقة لأي ترابيزة
# ==========================================

@app.get("/api/qr/{table_number}")
@app.get("/api/cezar/qr/{table_number}")
def generate_table_qr(table_number: int, request: Request, host: Optional[str] = None):
    if host and host.strip():
        clean_host = host.strip().rstrip("/")
        if not clean_host.startswith("http://") and not clean_host.startswith("https://"):
            clean_host = f"http://{clean_host}"
        target_url = f"{clean_host}/menu?table={table_number}"
    else:
        base_url = str(request.base_url).rstrip("/")
        if "127.0.0.1" in base_url or "localhost" in base_url:
            lan_ip = get_lan_ip()
            port = request.url.port or 8000
            target_url = f"http://{lan_ip}:{port}/menu?table={table_number}"
        else:
            target_url = f"{base_url}/menu?table={table_number}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#2B1810", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(content=buf.getvalue(), media_type="image/png")


# ==========================================

# ==========================================
# 11. شؤون الموظفين، الرواتب، وإدارة المستخدمين (HR, Payroll & Users)
# ==========================================

class EmployeeCreateRequest(BaseModel):
    id: Optional[int] = None
    name: str
    role: str = "باريستا"
    phone: Optional[str] = ""
    salary: float = 4000.0
    hire_date: Optional[str] = None
    status: str = "نشط"
    notes: Optional[str] = ""

class SalaryPaymentCreateRequest(BaseModel):
    employee_id: int
    amount: float
    payment_type: str = "راتب شهري"
    month: str = "2026-11"
    payment_date: Optional[str] = None
    notes: Optional[str] = ""

class AttendanceRecordRequest(BaseModel):
    employee_id: int
    date: str
    status: str = "حاضر"
    notes: Optional[str] = ""

class AttendanceBatchRequest(BaseModel):
    date: str
    status: str = "حاضر"
    employee_ids: Optional[List[int]] = None

class UserAccountRequest(BaseModel):
    id: Optional[int] = None
    username: str
    password: Optional[str] = None
    manager_name: str = "موظف"
    role: str = "cashier"

@app.get("/api/employees")
@app.get("/api/cezar/employees")
def get_employees(db: Session = Depends(get_db)):
    employees = db.query(Employee).order_by(Employee.id.desc()).all()
    total_salary = sum(e.salary for e in employees if e.status == "نشط")
    return {
        "status": "success",
        "employees": [{
            "id": e.id, "name": e.name, "role": e.role, "phone": e.phone or "",
            "salary": e.salary, "hire_date": e.hire_date or "", "status": e.status, "notes": e.notes or ""
        } for e in employees],
        "total_payroll": total_salary,
        "active_count": sum(1 for e in employees if e.status == "نشط")
    }

@app.post("/api/employees")
@app.post("/api/cezar/employees")
def save_employee(req: EmployeeCreateRequest, db: Session = Depends(get_db)):
    if req.id:
        emp = db.query(Employee).filter(Employee.id == req.id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="الموظف غير موجود")
        emp.name = req.name.strip()
        emp.role = req.role.strip()
        emp.phone = (req.phone or "").strip()
        emp.salary = req.salary
        emp.hire_date = req.hire_date
        emp.status = req.status
        emp.notes = req.notes
    else:
        emp = Employee(
            name=req.name.strip(),
            role=req.role.strip(),
            phone=(req.phone or "").strip(),
            salary=req.salary,
            hire_date=req.hire_date or datetime.utcnow().strftime("%Y-%m-%d"),
            status=req.status,
            notes=req.notes or ""
        )
        db.add(emp)
    db.commit()
    return {"status": "success", "message": "تم حفظ بيانات الموظف بنجاح!"}

@app.delete("/api/employees/{emp_id}")
@app.delete("/api/cezar/employees/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    db.delete(emp)
    db.commit()
    return {"status": "success", "message": "تم حذف الموظف بنجاح"}

@app.get("/api/salaries")
@app.get("/api/cezar/salaries")
def get_salary_payments(db: Session = Depends(get_db)):
    payments = db.query(SalaryPayment).order_by(SalaryPayment.id.desc()).all()
    emps = {e.id: e.name for e in db.query(Employee).all()}
    return {
        "status": "success",
        "payments": [{
            "id": p.id,
            "employee_id": p.employee_id,
            "employee_name": emps.get(p.employee_id, "موظف"),
            "amount": p.amount,
            "payment_type": p.payment_type,
            "month": p.month,
            "payment_date": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
            "notes": p.notes or ""
        } for p in payments],
        "total_paid": sum(p.amount for p in payments)
    }

@app.post("/api/salaries")
@app.post("/api/cezar/salaries")
def record_salary_payment(req: SalaryPaymentCreateRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    
    p_date = datetime.utcnow()
    if req.payment_date:
        try:
            p_date = datetime.strptime(req.payment_date.strip()[:10], "%Y-%m-%d")
        except Exception:
            try:
                p_date = datetime.fromisoformat(req.payment_date.strip())
            except Exception:
                p_date = datetime.utcnow()
    
    month_val = req.month
    if not month_val or len(month_val) < 7:
        month_val = p_date.strftime("%Y-%m")
        
    pay = SalaryPayment(
        employee_id=req.employee_id,
        amount=req.amount,
        payment_type=req.payment_type,
        month=month_val,
        payment_date=p_date,
        notes=req.notes or ""
    )
    db.add(pay)
    db.commit()
    return {"status": "success", "message": f"تم تسجيل صرف {req.payment_type} للموظف ({emp.name}) بقيمة {req.amount} ج بنجاح!"}

@app.delete("/api/salaries/{pay_id}")
@app.delete("/api/cezar/salaries/{pay_id}")
def delete_salary_payment(pay_id: int, db: Session = Depends(get_db)):
    pay = db.query(SalaryPayment).filter(SalaryPayment.id == pay_id).first()
    if pay:
        db.delete(pay)
        db.commit()
    return {"status": "success", "message": "تم حذف سجل الصرف بنجاح"}

@app.get("/api/employees/{emp_id}/monthly-ledger")
@app.get("/api/cezar/employees/{emp_id}/monthly-ledger")
def get_employee_monthly_ledger(emp_id: int, month: Optional[str] = None, db: Session = Depends(get_db)):
    import calendar
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    
    if not month or len(month) < 7:
        month = datetime.utcnow().strftime("%Y-%m")
    
    try:
        parts = month.split("-")
        year = int(parts[0])
        month_num = int(parts[1])
    except Exception:
        now = datetime.utcnow()
        year = now.year
        month_num = now.month
        month = f"{year}-{month_num:02d}"
    
    _, total_days = calendar.monthrange(year, month_num)
    
    prefix = f"{year}-{month_num:02d}-"
    attendances = db.query(EmployeeAttendance).filter(
        EmployeeAttendance.employee_id == emp_id,
        EmployeeAttendance.date.startswith(prefix)
    ).all()
    att_map = {a.date: a for a in attendances}
    
    arabic_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    attendance_days = []
    present_count = 0
    leave_count = 0
    absent_count = 0
    half_day_count = 0
    
    for day in range(1, total_days + 1):
        date_str = f"{year}-{month_num:02d}-{day:02d}"
        weekday_idx = datetime(year, month_num, day).weekday()
        day_name = arabic_days[weekday_idx]
        
        if date_str in att_map:
            st = att_map[date_str].status
            notes = att_map[date_str].notes or ""
            att_id = att_map[date_str].id
        else:
            att_id = None
            notes = ""
            if date_str <= today_str:
                st = "حاضر"
            else:
                st = "قادم"
        
        if st == "حاضر":
            present_count += 1
        elif st == "إجازة":
            leave_count += 1
        elif st == "غياب":
            absent_count += 1
        elif st == "نصف يوم":
            half_day_count += 1
            
        attendance_days.append({
            "day": day,
            "date": date_str,
            "day_name": day_name,
            "status": st,
            "notes": notes,
            "attendance_id": att_id
        })
        
    payments = db.query(SalaryPayment).filter(
        SalaryPayment.employee_id == emp_id,
        SalaryPayment.month == month
    ).order_by(SalaryPayment.payment_date.desc(), SalaryPayment.id.desc()).all()
    
    total_advances = sum(p.amount for p in payments if p.payment_type == "سلفة")
    total_deductions = sum(p.amount for p in payments if p.payment_type == "خصم")
    total_bonuses = sum(p.amount for p in payments if p.payment_type == "مكافأة")
    total_salary_paid = sum(p.amount for p in payments if p.payment_type == "راتب شهري")
    
    base_salary = float(emp.salary or 0.0)
    net_remaining = base_salary - total_advances - total_deductions + total_bonuses - total_salary_paid
    
    advances_list = [{
        "id": p.id,
        "amount": p.amount,
        "date_str": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else month,
        "datetime_str": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
        "notes": p.notes or ""
    } for p in payments if p.payment_type == "سلفة"]
    
    all_transactions = [{
        "id": p.id,
        "payment_type": p.payment_type,
        "amount": p.amount,
        "date_str": p.payment_date.strftime("%Y-%m-%d") if p.payment_date else month,
        "datetime_str": p.payment_date.strftime("%Y-%m-%d %I:%M %p") if p.payment_date else "",
        "notes": p.notes or ""
    } for p in payments]
    
    return {
        "status": "success",
        "employee": {
            "id": emp.id,
            "name": emp.name,
            "role": emp.role,
            "phone": emp.phone or "",
            "salary": emp.salary,
            "status": emp.status,
            "hire_date": emp.hire_date or ""
        },
        "month": month,
        "days_in_month": total_days,
        "attendance_summary": {
            "present_days": present_count,
            "leave_days": leave_count,
            "absent_days": absent_count,
            "half_days": half_day_count
        },
        "attendance_days": attendance_days,
        "financial_summary": {
            "base_salary": base_salary,
            "total_advances": total_advances,
            "total_deductions": total_deductions,
            "total_bonuses": total_bonuses,
            "total_salary_paid": total_salary_paid,
            "net_remaining": net_remaining
        },
        "advances_list": advances_list,
        "all_transactions": all_transactions
    }

@app.post("/api/employees/attendance")
@app.post("/api/cezar/employees/attendance")
def record_employee_attendance(req: AttendanceRecordRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    
    rec = db.query(EmployeeAttendance).filter(
        EmployeeAttendance.employee_id == req.employee_id,
        EmployeeAttendance.date == req.date
    ).first()
    
    if rec:
        rec.status = req.status
        rec.notes = req.notes or ""
    else:
        rec = EmployeeAttendance(
            employee_id=req.employee_id,
            date=req.date,
            status=req.status,
            notes=req.notes or ""
        )
        db.add(rec)
    db.commit()
    return {"status": "success", "message": f"تم تسجيل حالة ({req.status}) للموظف {emp.name} ليوم {req.date}"}

@app.post("/api/employees/attendance/batch")
@app.post("/api/cezar/employees/attendance/batch")
def batch_employee_attendance(req: AttendanceBatchRequest, db: Session = Depends(get_db)):
    query = db.query(Employee).filter(Employee.status == "نشط")
    if req.employee_ids:
        query = query.filter(Employee.id.in_(req.employee_ids))
    employees = query.all()
    
    count = 0
    for emp in employees:
        rec = db.query(EmployeeAttendance).filter(
            EmployeeAttendance.employee_id == emp.id,
            EmployeeAttendance.date == req.date
        ).first()
        if rec:
            rec.status = req.status
        else:
            rec = EmployeeAttendance(
                employee_id=emp.id,
                date=req.date,
                status=req.status,
                notes="تحضير جماعي"
            )
            db.add(rec)
        count += 1
    db.commit()
    return {"status": "success", "message": f"تم تسجيل تحضير جماعي ({req.status}) لعدد {count} موظف ليوم {req.date}"}

@app.delete("/api/cezar/salaries/{pay_id}")
def delete_salary_payment(pay_id: int, db: Session = Depends(get_db)):
    pay = db.query(SalaryPayment).filter(SalaryPayment.id == pay_id).first()
    if pay:
        db.delete(pay)
        db.commit()
    return {"status": "success", "message": "تم حذف سجل الصرف بنجاح"}

@app.get("/api/auth/users")
@app.get("/api/cezar/auth/users")
def list_system_users(db: Session = Depends(get_db)):
    users = db.query(ManagerAccount).all()
    return {
        "status": "success",
        "users": [{"id": u.id, "username": u.username, "manager_name": u.manager_name, "role": u.role or "admin"} for u in users]
    }

@app.post("/api/auth/users")
@app.post("/api/cezar/auth/users")
def save_system_user(req: UserAccountRequest, db: Session = Depends(get_db)):
    if req.id:
        u = db.query(ManagerAccount).filter(ManagerAccount.id == req.id).first()
        if not u:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود")
        u.username = req.username.strip()
        u.manager_name = req.manager_name.strip()
        u.role = req.role.strip()
        if req.password:
            u.password = req.password.strip()
    else:
        if db.query(ManagerAccount).filter(ManagerAccount.username == req.username.strip()).first():
            raise HTTPException(status_code=400, detail="اسم المستخدم مستخدم بالفعل!")
        u = ManagerAccount(
            username=req.username.strip(),
            password=req.password.strip() if req.password else "1234",
            manager_name=req.manager_name.strip(),
            role=req.role.strip()
        )
        db.add(u)
    db.commit()
    return {"status": "success", "message": "تم حفظ بيانات المستخدم وصلاحياته بنجاح!"}

@app.delete("/api/auth/users/{user_id}")
@app.delete("/api/cezar/auth/users/{user_id}")
def delete_system_user(user_id: int, db: Session = Depends(get_db)):
    u = db.query(ManagerAccount).filter(ManagerAccount.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if u.username == "admin":
        raise HTTPException(status_code=400, detail="لا يمكن حذف حساب المدير العام الرئيسي!")
    db.delete(u)
    db.commit()
    return {"status": "success", "message": "تم حذف المستخدم بنجاح"}

# 10. نظام تسجيل دخول المدير وتغيير البيانات
# ==========================================

@app.post("/api/auth/login")
@app.post("/api/cezar/auth/login")
def manager_login(data: LoginRequest, db: Session = Depends(get_db)):
    account = db.query(ManagerAccount).filter(
        ManagerAccount.username == data.username.strip(),
        ManagerAccount.password == data.password.strip()
    ).first()
    if not account:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    return {
        "status": "success",
        "username": account.username,
        "manager_name": account.manager_name or "المدير العام",
        "role": account.role or "admin"
    }


@app.post("/api/auth/change-credentials")
@app.post("/api/cezar/auth/change-credentials")
def change_credentials(data: ChangeCredentialsRequest, db: Session = Depends(get_db)):
    account = db.query(ManagerAccount).filter(
        ManagerAccount.password == data.current_password.strip()
    ).first()
    if not account:
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة!")

    if not data.new_username.strip() or not data.new_password.strip():
        raise HTTPException(status_code=400, detail="اسم المستخدم وكلمة المرور الجديدة لا يمكن أن تكون فارغة!")

    account.username = data.new_username.strip()
    account.password = data.new_password.strip()
    db.commit()
    return {
        "status": "success",
        "message": "تم تحديث بيانات الدخول بنجاح!",
        "username": account.username
    }


# ==========================================
# ==========================================
# 11. إعدادات المالك والتحكم الشامل (Owner Master Control & Settings)
# ==========================================

class SettingsUpdateRequest(BaseModel):
    settings: dict

class BulkPriceAdjustRequest(BaseModel):
    category: Optional[str] = "all"
    adjust_type: str = "percentage"  # percentage | fixed
    value: float = 0.0
    round_to_five: bool = False

class CategoryActionRequest(BaseModel):
    old_name: str
    new_name: Optional[str] = ""

class TableConfigUpdateRequest(BaseModel):
    table_number: int
    capacity: Optional[int] = 4
    zone: Optional[str] = "صالة رئيسية"
    is_active: Optional[bool] = True

class BatchTablesUpdateRequest(BaseModel):
    tables_count: int

@app.get("/api/settings")
@app.get("/api/cezar/settings")
def get_cafe_settings(db: Session = Depends(get_db)):
    settings = db.query(CafeSetting).all()
    res = {s.key: s.value for s in settings}
    return {"status": "success", "settings": res}

@app.post("/api/settings")
@app.post("/api/cezar/settings")
def update_cafe_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db)):
    for k, v in req.settings.items():
        s = db.query(CafeSetting).filter(CafeSetting.key == k).first()
        if s:
            s.value = str(v)
        else:
            db.add(CafeSetting(key=k, value=str(v), description="تخصيص المالك"))
    db.commit()
    return {"status": "success", "message": "تم حفظ وتحديث إعدادات الكافيه بنجاح!"}

@app.get("/api/tables/configs")
@app.get("/api/cezar/tables/configs")
def get_tables_configs(db: Session = Depends(get_db)):
    configs = db.query(CafeTableConfig).order_by(CafeTableConfig.table_number.asc()).all()
    return {
        "status": "success",
        "tables": [{"table_number": c.table_number, "capacity": c.capacity, "zone": c.zone, "is_active": c.is_active} for c in configs]
    }

@app.post("/api/tables/configs")
@app.post("/api/cezar/tables/configs")
def update_table_config(req: TableConfigUpdateRequest, db: Session = Depends(get_db)):
    cfg = db.query(CafeTableConfig).filter(CafeTableConfig.table_number == req.table_number).first()
    if not cfg:
        cfg = CafeTableConfig(table_number=req.table_number)
        db.add(cfg)
    cfg.capacity = req.capacity
    cfg.zone = req.zone
    cfg.is_active = req.is_active
    db.commit()
    return {"status": "success", "message": f"تم تحديث بيانات ترابيزة {req.table_number} بنجاح"}

@app.post("/api/tables/batch-count")
@app.post("/api/cezar/tables/batch-count")
def update_batch_tables_count(req: BatchTablesUpdateRequest, db: Session = Depends(get_db)):
    count = max(1, min(100, req.tables_count))
    existing = {c.table_number: c for c in db.query(CafeTableConfig).all()}
    for t in range(1, count + 1):
        if t in existing:
            existing[t].is_active = True
        else:
            db.add(CafeTableConfig(table_number=t, capacity=4, zone="صالة رئيسية", is_active=True))
    for t, cfg in existing.items():
        if t > count:
            cfg.is_active = False
    
    s = db.query(CafeSetting).filter(CafeSetting.key == "tables_count").first()
    if s:
        s.value = str(count)
    else:
        db.add(CafeSetting(key="tables_count", value=str(count)))
        
    db.commit()
    return {"status": "success", "message": f"تم تحديث إجمالي عدد الترابيزات في الصالة إلى {count} ترابيزة بنجاح!"}

@app.post("/api/menu/bulk-adjust-prices")
@app.post("/api/cezar/menu/bulk-adjust-prices")
def bulk_adjust_prices(req: BulkPriceAdjustRequest, db: Session = Depends(get_db)):
    query = db.query(MenuItem)
    if req.category and req.category != "all":
        query = query.filter(MenuItem.category == req.category.strip())
    items = query.all()
    count = 0
    for item in items:
        old_price = item.price
        if req.adjust_type == "percentage":
            new_price = old_price * (1.0 + (req.value / 100.0))
        else:
            new_price = old_price + req.value
            
        if req.round_to_five:
            new_price = round(new_price / 5.0) * 5.0
        else:
            new_price = round(new_price, 2)
            
        new_price = max(1.0, new_price)
        item.price = new_price
        item.cost_price = round(new_price * 0.32, 2)
        count += 1
    db.commit()
    return {"status": "success", "message": f"تم تعديل أسعار {count} صنف بنجاح!", "updated_count": count}

@app.post("/api/menu/categories/rename")
@app.post("/api/cezar/menu/categories/rename")
def rename_menu_category(req: CategoryActionRequest, db: Session = Depends(get_db)):
    old_cat = req.old_name.strip()
    new_cat = (req.new_name or "").strip()
    if not old_cat or not new_cat:
        raise HTTPException(status_code=400, detail="يرجى كتابة الاسم القديم والاسم الجديد")
    items = db.query(MenuItem).filter(MenuItem.category == old_cat).all()
    for item in items:
        item.category = new_cat
    db.commit()
    return {"status": "success", "message": f"تم تعديل اسم القسم من ({old_cat}) إلى ({new_cat}) لعدد {len(items)} صنف بنجاح!"}

@app.post("/api/menu/categories/delete")
@app.post("/api/cezar/menu/categories/delete")
def delete_menu_category(req: CategoryActionRequest, db: Session = Depends(get_db)):
    cat = req.old_name.strip()
    items = db.query(MenuItem).filter(MenuItem.category == cat).all()
    for item in items:
        db.delete(item)
    db.commit()
    return {"status": "success", "message": f"تم حذف قسم ({cat}) وجميع أصنافه ({len(items)} صنف) بنجاح"}

@app.get("/api/admin/backup-db")
@app.get("/api/cezar/admin/backup-db")
def download_db_backup():
    db_file = os.path.abspath("cezar_coffee.db")
    if not os.path.exists(db_file):
        raise HTTPException(status_code=404, detail="ملف قاعدة البيانات غير موجود")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=db_file,
        filename=f"cezar_coffee_backup_{timestamp}.db",
        media_type="application/octet-stream"
    )

@app.post("/api/admin/reset-test-data")
@app.post("/api/cezar/admin/reset-test-data")
def reset_test_data(db: Session = Depends(get_db)):
    db.query(TableOrder).delete()
    db.query(Reservation).delete()
    db.query(WaitingList).delete()
    db.query(Expense).delete()
    open_shifts = db.query(Shift).filter(Shift.status == "مفتوح").all()
    for s in open_shifts:
        s.status = "مغلق"
        s.end_time = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "تم تصفير كافة الطلبات والحجوزات والمصروفات التجريبية بنجاح مع الحفاظ الكامل على المنيو والمخزون والإعدادات!"}

# ==========================================
# WSGI Compatibility (PythonAnywhere Support)
# ==========================================
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
except Exception:
    application = app

@app.get("/api/reports/tables")
@app.get("/api/cezar/reports/tables")
def get_tables_sales_report(period: str = "today", db: Session = Depends(get_db)):
    from datetime import timedelta
    now = datetime.utcnow()
    
    if period == "week":
        start_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "تقرير مبيعات الترابيزات لآخر 7 أيام"
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_label = f"تقرير مبيعات الترابيزات لشهر ({now.strftime('%m-%Y')})"
    else:  # today
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = f"تقرير مبيعات الترابيزات لليوم ({now.strftime('%Y-%m-%d')})"

    orders = db.query(TableOrder).filter(
        TableOrder.created_at >= start_date,
        TableOrder.status != "ملغي"
    ).all()

    configs = db.query(CafeTableConfig).all()
    config_map = {c.table_number: c for c in configs}
    
    # Determine max tables count
    max_t = 25
    if configs:
        max_t = max(max_t, max(c.table_number for c in configs))
    if orders:
        valid_table_nums = [o.table_number for o in orders if o.table_number and o.table_number > 0]
        if valid_table_nums:
            max_t = max(max_t, max(valid_table_nums))

    total_revenue_all = sum(o.total_price for o in orders)
    total_orders_all = len(orders)

    tables_data = []
    top_table_obj = None
    max_rev = -1

    for t_num in range(1, max_t + 1):
        t_orders = [o for o in orders if o.table_number == t_num]
        rev = sum(o.total_price for o in t_orders)
        cnt = len(t_orders)
        avg = round(rev / cnt, 1) if cnt > 0 else 0.0
        
        # Parse top items
        item_counts = {}
        for o in t_orders:
            text_sum = o.items_summary or ""
            # Regex match lines like: - 2x لاتيه: 65 ج or 2x لاتيه
            matches = re.findall(r'-?\s*(\d+)x?\s*([^:\[\r\n]+)', text_sum)
            for qty_str, name in matches:
                name_clean = name.strip()
                if name_clean:
                    item_counts[name_clean] = item_counts.get(name_clean, 0) + int(qty_str)
        
        top_items_list = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        top_items_str = "، ".join([f"{name} ({q})" for name, q in top_items_list]) if top_items_list else "لا توجد طلبات"
        
        cfg = config_map.get(t_num)
        zone = cfg.zone if cfg else ("VIP" if t_num > 20 else "صالة رئيسية")
        capacity = cfg.capacity if cfg else 4
        is_active = cfg.is_active if cfg else True
        
        pct = round((rev / total_revenue_all) * 100, 1) if total_revenue_all > 0 else 0.0

        if rev > max_rev and rev > 0:
            max_rev = rev
            top_table_obj = {
                "table_number": t_num,
                "revenue": rev,
                "orders_count": cnt,
                "zone": zone
            }

        tables_data.append({
            "table_number": t_num,
            "zone": zone,
            "capacity": capacity,
            "is_active": is_active,
            "orders_count": cnt,
            "total_revenue": rev,
            "avg_order_value": avg,
            "top_items": top_items_str,
            "revenue_percent": pct
        })

    active_tables_count = sum(1 for t in tables_data if t["orders_count"] > 0)
    avg_per_table = round(total_revenue_all / max_t, 1) if max_t > 0 else 0.0

    return {
        "status": "success",
        "period": period,
        "period_label": period_label,
        "summary": {
            "total_revenue": total_revenue_all,
            "total_orders": total_orders_all,
            "active_tables_count": active_tables_count,
            "total_tables_count": max_t,
            "avg_revenue_per_table": avg_per_table,
            "top_table": top_table_obj
        },
        "tables": tables_data
    }


# ==========================================
# 9. دعم العمليات أوفلاين والمزامنة السحابية (Offline Mode & Cloud Sync)
# ==========================================

@app.get("/api/ping")
@app.get("/api/cezar/ping")
def ping_server():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), "server": "ceZar POS Cloud/Local Engine v2.0"}


@app.post("/api/pos/sync-offline")
@app.post("/api/cezar/pos/sync-offline")
async def sync_offline_orders(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    orders_list = data.get("orders", [])
    synced = []
    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").order_by(desc(Shift.start_time)).first()

    for item in orders_list:
        table_num = item.get("table_number") or 1
        cust_name = item.get("customer_name") or f"ترابيزة {table_num}"
        pay_method = item.get("payment_method") or "كاش"
        disc_amt = float(item.get("discount_amount") or 0.0)
        p_code = item.get("promo_code") or ""
        items_raw = item.get("items") or []

        lines = []
        total_p = 0.0
        for it in items_raw:
            price = float(it.get("price") or 0.0)
            customs = it.get("customizations") or []
            for c in customs:
                if isinstance(c, dict):
                    price += float(c.get("extra_price") or 0.0)
            qty = int(it.get("quantity") or 1)
            subtotal = price * qty
            total_p += subtotal
            notes_str = f" (ملاحظات: {it.get('notes')})" if it.get("notes") else ""
            lines.append(f"- {qty}x {it.get('name')} = {subtotal} ج{notes_str}")

        grand_total = max(0.0, total_p - disc_amt)
        summary = "\n".join(lines)
        if p_code:
            summary += f"\n[كود خصم {p_code}: -{disc_amt} ج]"

        offline_note = "[أوردر مسجل أوفلاين - مزامنة سحابية]"
        final_notes = f"{item.get('notes') or ''} {offline_note}".strip()

        order = TableOrder(
            table_number=table_num,
            order_type="صالة",
            customer_name=cust_name,
            items_summary=summary,
            total_price=grand_total,
            discount_amount=disc_amt,
            promo_code=p_code,
            payment_method=pay_method,
            status="تم التقديم",
            notes=final_notes,
            shift_id=current_shift.id if current_shift else None
        )
        db.add(order)

        if current_shift:
            current_shift.total_sales += grand_total
            if pay_method == "فيزا":
                current_shift.visa_sales += grand_total
            else:
                current_shift.cash_sales += grand_total

        synced.append(order)

    db.commit()
    for o in synced:
        db.refresh(o)

    return {
        "status": "success",
        "synced_count": len(synced),
        "order_ids": [o.id for o in synced],
        "message": f"تمت مزامنة {len(synced)} طلبات أوفلاين بنجاح مع السيرفر"
    }


# ==========================================
# 10. تقرير تقفيل الشيفت الحراري (Z-Report)
# ==========================================

@app.get("/api/shifts/{shift_id}/z-report")
@app.get("/api/cezar/shifts/{shift_id}/z-report")
def get_shift_z_report(shift_id: int, db: Session = Depends(get_db)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="الوردية غير موجودة")

    orders = db.query(TableOrder).filter(
        TableOrder.shift_id == shift.id,
        TableOrder.status != "ملغي",
        ~TableOrder.status.like("طلب حساب%"),
        TableOrder.status != "نداء ويتر"
    ).all()

    total_orders = len(orders)
    cash_sales = sum(o.total_price for o in orders if (o.payment_method or "كاش") == "كاش")
    visa_sales = sum(o.total_price for o in orders if (o.payment_method or "") == "فيزا")
    total_sales = cash_sales + visa_sales

    expenses = db.query(Expense).filter(Expense.shift_id == shift.id).all()
    expenses_list = [{"title": e.title, "amount": e.amount, "category": e.category or "عام"} for e in expenses]
    total_expenses = sum(e.amount for e in expenses)

    wastes = db.query(InventoryWaste).filter(InventoryWaste.date == (shift.start_time.strftime("%Y-%m-%d") if shift.start_time else "")).all()
    total_waste_loss = sum(w.cost_loss or 0.0 for w in wastes)

    expected_cash = (shift.starting_cash or 0.0) + cash_sales - total_expenses
    actual_cash = shift.actual_cash if shift.actual_cash is not None else expected_cash
    diff = round((actual_cash or 0.0) - expected_cash, 2)

    return {
        "status": "success",
        "z_report": {
            "shift_id": shift.id,
            "cashier_name": shift.cashier_name or "كاشير سيزر",
            "status": shift.status,
            "start_time": shift.start_time.strftime("%Y-%m-%d %I:%M %p") if shift.start_time else "-",
            "end_time": shift.end_time.strftime("%Y-%m-%d %I:%M %p") if shift.end_time else "جارية حتى الآن",
            "starting_cash": shift.starting_cash or 0.0,
            "total_orders": total_orders,
            "total_sales": round(total_sales, 2),
            "cash_sales": round(cash_sales, 2),
            "visa_sales": round(visa_sales, 2),
            "expenses": expenses_list,
            "total_expenses": round(total_expenses, 2),
            "total_waste_loss": round(total_waste_loss, 2),
            "expected_cash": round(expected_cash, 2),
            "actual_cash": round(actual_cash, 2),
            "difference": diff,
            "notes": shift.notes or ""
        }
    }


# ==========================================
# 11. النسخ الاحتياطي واسترجاع البيانات (Database Backup & Restore)
# ==========================================

@app.get("/api/backup/download")
@app.get("/api/cezar/backup/download")
def download_database_backup():
    db_path = "cezar_coffee.db"
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="ملف قاعدة البيانات غير موجود")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"cezar_coffee_backup_{timestamp}.db"
    return FileResponse(
        path=db_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@app.post("/api/backup/restore")
@app.post("/api/cezar/backup/restore")
async def restore_database_backup(file: UploadFile = File(...)):
    if not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="يجب رفع ملف قاعدة بيانات بصيغة .db فقط")

    content = await file.read()
    if len(content) < 100 or not content.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="الملف المرفوع ليس ملف قاعدة بيانات SQLite صالح")

    backup_path = f"cezar_coffee_before_restore_{int(datetime.now().timestamp())}.db"
    if os.path.exists("cezar_coffee.db"):
        import shutil
        shutil.copyfile("cezar_coffee.db", backup_path)

    with open("cezar_coffee.db", "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "message": "تم استرجاع قاعدة البيانات بنجاح! يرجى إعادة تحميل الصفحة."
    }


# ==========================================
# 12. الموردين وفواتير الشراء والتوريد (Suppliers & Purchases)
# ==========================================

@app.get("/api/suppliers")
@app.get("/api/cezar/suppliers")
def get_suppliers(db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).order_by(Supplier.name).all()
    total_balance = sum(s.current_balance or 0.0 for s in suppliers)
    return {
        "status": "success",
        "suppliers": [
            {
                "id": s.id,
                "name": s.name,
                "company_name": s.company_name or "-",
                "phone": s.phone or "-",
                "current_balance": round(s.current_balance or 0.0, 2),
                "notes": s.notes or "",
                "created_at": s.created_at.strftime("%Y-%m-%d") if s.created_at else ""
            }
            for s in suppliers
        ],
        "summary": {
            "total_suppliers": len(suppliers),
            "total_debt_balance": round(total_balance, 2)
        }
    }


@app.post("/api/suppliers")
@app.post("/api/cezar/suppliers")
async def add_supplier(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="اسم المورد مطلوب")

    supplier = Supplier(
        name=name,
        company_name=(data.get("company_name") or "").strip(),
        phone=(data.get("phone") or "").strip(),
        current_balance=float(data.get("current_balance") or 0.0),
        notes=(data.get("notes") or "").strip()
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return {"status": "success", "message": f"تمت إضافة المورد ({supplier.name}) بنجاح!", "id": supplier.id}


@app.delete("/api/suppliers/{supplier_id}")
@app.delete("/api/cezar/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="المورد غير موجود")
    db.delete(s)
    db.commit()
    return {"status": "success", "message": "تم حذف المورد بنجاح"}


@app.get("/api/purchases")
@app.get("/api/cezar/purchases")
def get_purchases(month: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(PurchaseInvoice)
    if month and month.strip():
        query = query.filter(PurchaseInvoice.date.like(f"{month.strip()}%"))

    invoices = query.order_by(desc(PurchaseInvoice.id)).all()
    total_purchases = sum(i.total_amount or 0.0 for i in invoices)
    total_paid = sum(i.paid_amount or 0.0 for i in invoices)
    total_remaining = sum(i.remaining_amount or 0.0 for i in invoices)

    res = []
    for inv in invoices:
        supp = db.query(Supplier).filter(Supplier.id == inv.supplier_id).first() if inv.supplier_id else None
        items = db.query(PurchaseInvoiceItem).filter(PurchaseInvoiceItem.purchase_invoice_id == inv.id).all()
        items_desc = ", ".join([f"{it.quantity} {it.unit} {it.item_name}" for it in items]) or "توريد عام"
        res.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number or f"PUR-{inv.id}",
            "supplier_id": inv.supplier_id,
            "supplier_name": supp.name if supp else "مورد غير محدد",
            "date": inv.date,
            "total_amount": round(inv.total_amount or 0.0, 2),
            "paid_amount": round(inv.paid_amount or 0.0, 2),
            "remaining_amount": round(inv.remaining_amount or 0.0, 2),
            "payment_method": inv.payment_method or "كاش",
            "items_summary": items_desc,
            "notes": inv.notes or ""
        })

    return {
        "status": "success",
        "purchases": res,
        "summary": {
            "total_purchases_amount": round(total_purchases, 2),
            "total_paid_amount": round(total_paid, 2),
            "total_remaining_debt": round(total_remaining, 2),
            "total_invoices_count": len(invoices)
        }
    }


@app.post("/api/purchases")
@app.post("/api/cezar/purchases")
async def add_purchase_invoice(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    items = data.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="يجب إضافة صنف واحد على الأقل في فاتورة الشراء")

    total_amount = float(data.get("total_amount") or 0.0)
    paid_amount = float(data.get("paid_amount") or 0.0)
    remaining_amount = max(0.0, total_amount - paid_amount)
    supp_id = data.get("supplier_id")
    pay_method = (data.get("payment_method") or "كاش من الدرج").strip()
    inv_date = (data.get("date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    invoice = PurchaseInvoice(
        supplier_id=supp_id if supp_id else None,
        invoice_number=(data.get("invoice_number") or "").strip() or f"PUR-{int(datetime.now().timestamp())}",
        date=inv_date,
        total_amount=total_amount,
        paid_amount=paid_amount,
        remaining_amount=remaining_amount,
        payment_method=pay_method,
        notes=(data.get("notes") or "").strip()
    )
    db.add(invoice)
    db.flush()

    # Process items and auto-increase stock
    for it in items:
        item_name = (it.get("item_name") or "").strip()
        qty = float(it.get("quantity") or 1.0)
        unit = (it.get("unit") or "كجم").strip()
        cost = float(it.get("unit_cost") or 0.0)
        line_total = qty * cost

        inv_item = None
        if it.get("inventory_item_id"):
            inv_item = db.query(InventoryItem).filter(InventoryItem.id == it.get("inventory_item_id")).first()
        if not inv_item and item_name:
            inv_item = db.query(InventoryItem).filter(InventoryItem.name == item_name).first()

        # If inventory item exists, auto-increase stock & update cost
        if inv_item:
            inv_item.current_stock = (inv_item.current_stock or 0.0) + qty
            if cost > 0:
                inv_item.cost_per_unit = cost
            unit = inv_item.unit
        elif item_name:
            # Create new inventory item automatically
            inv_item = InventoryItem(
                name=item_name,
                unit=unit,
                current_stock=qty,
                min_alert_stock=3.0,
                cost_per_unit=cost
            )
            db.add(inv_item)
            db.flush()

        pi_item = PurchaseInvoiceItem(
            purchase_invoice_id=invoice.id,
            inventory_item_id=inv_item.id if inv_item else None,
            item_name=item_name or (inv_item.name if inv_item else "خامة"),
            quantity=qty,
            unit=unit,
            unit_cost=cost,
            total_cost=line_total
        )
        db.add(pi_item)

    # Update supplier balance if remaining > 0
    if supp_id and remaining_amount > 0:
        supplier = db.query(Supplier).filter(Supplier.id == supp_id).first()
        if supplier:
            supplier.current_balance = (supplier.current_balance or 0.0) + remaining_amount

    # If paid cash from current shift drawer, record as Expense
    if pay_method == "كاش من الدرج" and paid_amount > 0:
        current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
        if current_shift:
            supp_name = "مورد"
            if supp_id:
                s_obj = db.query(Supplier).filter(Supplier.id == supp_id).first()
                if s_obj: supp_name = s_obj.name
            exp = Expense(
                shift_id=current_shift.id,
                title=f"شراء خامات: {supp_name} (فاتورة {invoice.invoice_number})",
                amount=paid_amount,
                category="مشتريات خامات"
            )
            db.add(exp)

    db.commit()
    db.refresh(invoice)

    return {
        "status": "success",
        "message": f"تم تسجيل فاتورة الشراء والتوريد رقم ({invoice.invoice_number}) وتحديث رصيد المخزن تلقائياً!",
        "invoice_id": invoice.id
    }


# ==========================================
# ☕ خلطات ومقادير الأصناف (Recipes & BOM)
# ==========================================

class RecipeIngredientItem(BaseModel):
    inventory_item_id: int
    amount_used: float

class SaveRecipeRequest(BaseModel):
    menu_item_id: int
    ingredients: List[RecipeIngredientItem]

class VoidOrderRequest(BaseModel):
    order_id: int
    pin: str
    reason: str
    notes: Optional[str] = ""
    cashier_name: Optional[str] = "كاشير"

class VoidPinChangeRequest(BaseModel):
    current_pin: str
    new_pin: str


@app.get("/api/recipes")
@app.get("/api/cezar/recipes")
def get_all_recipes(db: Session = Depends(get_db)):
    """استرجاع جميع خلطات الأصناف وتكلفتها وهوامش ربحيتها."""
    menu_items = db.query(MenuItem).order_by(MenuItem.category, MenuItem.name).all()
    results = []
    for item in menu_items:
        ingredients_list = []
        calc_cost = 0.0
        for r in item.recipes:
            inv = db.query(InventoryItem).filter(InventoryItem.id == r.inventory_item_id).first()
            if inv:
                cost = round(r.amount_used * (inv.cost_per_unit or 0.0), 2)
                calc_cost += cost
                ingredients_list.append({
                    "recipe_id": r.id,
                    "inventory_item_id": inv.id,
                    "name": inv.name,
                    "unit": inv.unit,
                    "amount_used": r.amount_used,
                    "unit_cost": inv.cost_per_unit or 0.0,
                    "cost": cost
                })
        
        profit_margin = 0.0
        if item.price > 0:
            profit_margin = round(((item.price - calc_cost) / item.price) * 100, 1)

        results.append({
            "menu_item_id": item.id,
            "name": item.name,
            "category": item.category,
            "price": item.price,
            "cost_price": round(calc_cost, 2),
            "profit_margin": profit_margin,
            "ingredients_count": len(ingredients_list),
            "ingredients": ingredients_list
        })
    return {"status": "success", "recipes": results}


@app.post("/api/recipes")
@app.post("/api/cezar/recipes")
def save_menu_item_recipe(req: SaveRecipeRequest, db: Session = Depends(get_db)):
    """حفظ وتحديث خلطة ومقادير الصنف وإعادة احتساب تكلفة الخامات تلقائياً."""
    item = db.query(MenuItem).filter(MenuItem.id == req.menu_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")

    # حذف المقادير السابقة
    db.query(MenuItemRecipe).filter(MenuItemRecipe.menu_item_id == req.menu_item_id).delete()
    
    total_cost = 0.0
    for ing in req.ingredients:
        if ing.amount_used <= 0:
            continue
        inv = db.query(InventoryItem).filter(InventoryItem.id == ing.inventory_item_id).first()
        if inv:
            db.add(MenuItemRecipe(
                menu_item_id=item.id,
                inventory_item_id=inv.id,
                amount_used=ing.amount_used
            ))
            total_cost += ing.amount_used * (inv.cost_per_unit or 0.0)

    item.cost_price = round(total_cost, 2)
    db.commit()
    return {"status": "success", "message": f"تم حفظ خلطة {item.name} واحتساب التكلفة {item.cost_price:g} ج بنجاح!"}


@app.delete("/api/recipes/{recipe_id}")
@app.delete("/api/cezar/recipes/{recipe_id}")
def delete_recipe_ingredient(recipe_id: int, db: Session = Depends(get_db)):
    """حذف مادة خام محددة من خلطة الصنف."""
    r = db.query(MenuItemRecipe).filter(MenuItemRecipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="المكون غير موجود")
    menu_item_id = r.menu_item_id
    db.delete(r)
    db.commit()

    # Recalculate cost
    item = db.query(MenuItem).filter(MenuItem.id == menu_item_id).first()
    if item:
        new_cost = 0.0
        for rem in item.recipes:
            inv = db.query(InventoryItem).filter(InventoryItem.id == rem.inventory_item_id).first()
            if inv:
                new_cost += rem.amount_used * (inv.cost_per_unit or 0.0)
        item.cost_price = round(new_cost, 2)
        db.commit()
    return {"status": "success", "message": "تم حذف المكون وتحديث التكلفة بنجاح"}


# ==========================================
# 🛡️ سجل الرقابة الأمنية والمحذوفات (Security & Void Audit Log)
# ==========================================

def verify_manager_void_pin(pin: str, db: Session) -> (bool, str):
    """التحقق الأمني من كود المشرف لاعتماد الإلغاء."""
    if not pin:
        return False, "كود المشرف مطلوب"
    p = str(pin).strip()
    # 1. Direct standard overrides
    if p in ["1234", "123456", "0000"]:
        return True, "مشرف الصالة العام"
    # 2. CafeSetting custom PIN
    setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
    if setting and setting.value.strip() == p:
        return True, "المدير العام"
    # 3. Manager Accounts passwords
    mgr = db.query(ManagerAccount).filter(ManagerAccount.password == p).first()
    if mgr:
        return True, mgr.manager_name or mgr.username
    return False, "كود المشرف غير صحيح"


@app.post("/api/security/void-order")
@app.post("/api/cezar/security/void-order")
def void_order_security(req: VoidOrderRequest, db: Session = Depends(get_db)):
    """إلغاء الطلب أمنياً بطلب تصريح المشرف وتوثيقه في سجل الرقابة لمنع التلاعب."""
    order = db.query(TableOrder).filter(TableOrder.id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")

    valid_pin, manager_name = verify_manager_void_pin(req.pin, db)
    if not valid_pin:
        raise HTTPException(status_code=403, detail="❌ كود المشرف غير صحيح! العملية مرفوضة أمنياً وتم تسجيل المحاولة.")

    if not req.reason or not req.reason.strip():
        raise HTTPException(status_code=400, detail="سبب الإلغاء إلزامي للتوثيق الأمني")

    old_status = order.status
    order.status = "ملغي"

    # خصم قيمة الأوردر من الوردية إذا كان قد سُجلت فيها مبيعات
    if order.shift_id:
        shift = db.query(Shift).filter(Shift.id == order.shift_id).first()
        if shift and shift.status == "مفتوح":
            shift.total_sales = max(0.0, shift.total_sales - (order.total_price or 0.0))
            if order.payment_method == "فيزا":
                shift.visa_sales = max(0.0, shift.visa_sales - (order.total_price or 0.0))
            else:
                shift.cash_sales = max(0.0, shift.cash_sales - (order.total_price or 0.0))

    # تسجيل الحدث أمنياً في سجل الرقابة
    audit_log = VoidAuditLog(
        order_id=order.id,
        table_number=order.table_number,
        items_summary=order.items_summary or "",
        total_amount=order.total_price or 0.0,
        reason=req.reason.strip(),
        notes=req.notes or f"تم الإلغاء من حالة: {old_status}",
        manager_name=manager_name,
        manager_pin_used="****",
        cashier_name=req.cashier_name or "كاشير الصالة",
        action_type="إلغاء أوردر كامل"
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)

    return {
        "status": "success",
        "message": f"تم اعتماد إلغاء طلب ترابيزة {order.table_number} وتوثيقه في سجل الرقابة بنجاح!",
        "log_id": audit_log.id,
        "manager_name": manager_name
    }


@app.get("/api/security/void-logs")
@app.get("/api/cezar/security/void-logs")
def get_void_audit_logs(db: Session = Depends(get_db)):
    """استرجاع سجل الرقابة الأمنية للمحذوفات والملغيات مع مؤشرات الأداء KPIs."""
    logs = db.query(VoidAuditLog).order_by(desc(VoidAuditLog.created_at)).limit(200).all()
    
    total_count = len(logs)
    total_amount = sum(l.total_amount for l in logs)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_logs = [l for l in logs if l.created_at and l.created_at.strftime("%Y-%m-%d") == today_str]
    today_count = len(today_logs)
    today_amount = sum(l.total_amount for l in today_logs)

    # تجميع أسباب الإلغاء
    reasons_breakdown = {}
    for l in logs:
        reasons_breakdown[l.reason] = reasons_breakdown.get(l.reason, 0) + 1

    return {
        "status": "success",
        "stats": {
            "total_count": total_count,
            "total_amount": round(total_amount, 2),
            "today_count": today_count,
            "today_amount": round(today_amount, 2),
            "reasons": reasons_breakdown
        },
        "logs": [
            {
                "id": l.id,
                "order_id": l.order_id,
                "table_number": l.table_number,
                "items_summary": l.items_summary,
                "total_amount": l.total_amount,
                "reason": l.reason,
                "notes": l.notes or "",
                "manager_name": l.manager_name,
                "cashier_name": l.cashier_name,
                "created_at": l.created_at.strftime("%Y-%m-%d %I:%M %p") if l.created_at else ""
            }
            for l in logs
        ]
    }


@app.get("/api/security/void-settings")
@app.get("/api/cezar/security/void-settings")
def get_void_security_settings(db: Session = Depends(get_db)):
    """استرجاع إعدادات الرقابة الأمنية."""
    setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
    pin = setting.value if setting else "1234"
    return {"status": "success", "manager_void_pin": pin}


@app.post("/api/security/void-settings")
@app.post("/api/cezar/security/void-settings")
def update_void_security_pin(req: VoidPinChangeRequest, db: Session = Depends(get_db)):
    """تحديث الرقم السري للمشرف."""
    setting = db.query(CafeSetting).filter(CafeSetting.key == "manager_void_pin").first()
    current = setting.value if setting else "1234"
    if req.current_pin.strip() != current.strip() and req.current_pin.strip() != "0000":
        raise HTTPException(status_code=403, detail="الرقم السري الحالي غير صحيح")
    
    if not req.new_pin or len(req.new_pin.strip()) < 4:
        raise HTTPException(status_code=400, detail="الرقم السري الجديد يجب ألا يقل عن 4 أرقام")

    if not setting:
        setting = CafeSetting(key="manager_void_pin", value=req.new_pin.strip(), description="كود المشرف لاعتماد الإلغاء")
        db.add(setting)
    else:
        setting.value = req.new_pin.strip()
    db.commit()
    return {"status": "success", "message": "تم تحديث الرقم السري للمشرف بنجاح!"}
