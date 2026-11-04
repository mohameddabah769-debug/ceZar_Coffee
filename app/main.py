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
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

from .database import engine, Base, SessionLocal, get_db
from .models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList, InventoryItem, PromoCode, MenuItemRecipe, Employee, SalaryPayment, CafeSetting, CafeTableConfig
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
    id: int
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
    """الخصم التلقائي للمواد الخام والمخزون عند إنشاء أو تحضير أي أوردر."""
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
    deduct_inventory_for_order(order_data.items, db)
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
        "total_salaries": total_salaries,
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

    # Calculate Food Cost (COGS) and Net Profit
    gross_sales = sum(o.total_price for o in orders)
    # Estimate COGS based on sold items (approx 32% food cost)
    total_cogs = round(gross_sales * 0.32, 2)
    total_expenses = db.query(func.sum(Expense.amount)).scalar() or 0.0
    total_salaries = db.query(func.sum(SalaryPayment.amount)).scalar() or 0.0
    net_profit = round(max(0.0, gross_sales - total_cogs - total_expenses - total_salaries), 2)
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
    notes: Optional[str] = ""

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
    
    pay = SalaryPayment(
        employee_id=req.employee_id,
        amount=req.amount,
        payment_type=req.payment_type,
        month=req.month,
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
