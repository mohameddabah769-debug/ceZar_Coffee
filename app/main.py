import os
import sys
import io
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
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

from .database import engine, Base, SessionLocal, get_db
from .models import MenuItem, TableOrder, ManagerAccount, Shift, Expense, Reservation, WaitingList
from .seed import seed_menu

# إنشاء الجداول تلقائياً
Base.metadata.create_all(bind=engine)

# تحديث الأعمدة الجديدة في جدول table_orders تلقائياً إذا كانت غير موجودة
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
        ]
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE table_orders ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

auto_migrate_columns()

# التأكد من وجود أصناف المنيو وحسابات المديرين
with SessionLocal() as db:
    seed_menu(db)
    if db.query(ManagerAccount).filter(ManagerAccount.username == "admin").count() == 0:
        db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
    if db.query(ManagerAccount).filter(ManagerAccount.username == "cezar").count() == 0:
        db.add(ManagerAccount(username="cezar", password="0000", manager_name="كافيه سيزر"))
    db.commit()

app = FastAPI(
    title="ceZar COFFEE - All-In-One POS & Management System",
    description="نظام إدارة المبيعات، الشيفتات، الحجوزات، والصالة والدليفري لكافيه سيزر كوفي",
    version="2.0.0"
)

# ربط الملفات الثابتة (اللوجو والصور)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def get_lan_ip():
    """كشف الآي بي المحلي لجهاز اللابتوب على شبكة الواي فاي تلقائياً لمسح الـ QR."""
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


class CreateTableOrderRequest(BaseModel):
    table_number: int
    items: List[TableOrderItem]
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None


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
    """استرجاع أصناف المنيو مقسمة بالأقسام. إذا كانت all_items=True تعيد الأصناف للإدارة."""
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

@app.post("/api/orders")
@app.post("/api/cezar/orders")
def create_table_order(order_data: CreateTableOrderRequest, db: Session = Depends(get_db)):
    if not order_data.items:
        raise HTTPException(status_code=400, detail="السلة فارغة")

    lines = []
    total = 0.0
    for item in order_data.items:
        item_total = item.price * item.quantity
        total += item_total
        lines.append(f"- {item.quantity}x {item.name}: {item_total:g} ج")

    items_summary = "\n".join(lines)

    # جلب الشيفت المفتوح حالياً لربط الأوردر به
    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    shift_id = current_shift.id if current_shift else None

    order = TableOrder(
        table_number=order_data.table_number,
        order_type="صالة",
        items_summary=items_summary,
        total_price=total,
        customer_name=order_data.customer_name or f"ترابيزة {order_data.table_number}",
        customer_phone=order_data.customer_phone or "",
        notes=order_data.notes or "",
        status="جديد",
        payment_method="كاش",
        shift_id=shift_id
    )
    db.add(order)

    # تحديث إجمالي مبيعات الشيفت
    if current_shift:
        current_shift.total_sales += total
        current_shift.cash_sales += total

    db.commit()
    db.refresh(order)
    return {
        "status": "success",
        "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
        "order_id": order.id,
        "table_number": order.table_number,
        "total_price": order.total_price
    }


@app.post("/api/pos/orders")
@app.post("/api/cezar/pos/orders")
def create_pos_direct_order(data: PosOrderCreateRequest, db: Session = Depends(get_db)):
    """إنشاء أوردر كاشير مباشر (صالة أو تيك أواي أو دليفري)."""
    if not data.items:
        raise HTTPException(status_code=400, detail="يجب إضافة صنف واحد على الأقل للأوردر")

    lines = []
    items_total = 0.0
    for item in data.items:
        item_total = item.price * item.quantity
        items_total += item_total
        lines.append(f"- {item.quantity}x {item.name}: {item_total:g} ج")

    delivery_fee = data.delivery_fee or 0.0 if data.order_type == "دليفري" else 0.0
    grand_total = items_total + delivery_fee
    items_summary = "\n".join(lines)

    current_shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    shift_id = current_shift.id if current_shift else None

    order = TableOrder(
        table_number=data.table_number if data.order_type == "صالة" else 0,
        order_type=data.order_type,
        items_summary=items_summary,
        total_price=grand_total,
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

    # تحديث مبيعات الشيفت
    if current_shift:
        current_shift.total_sales += grand_total
        if data.payment_method == "فيزا":
            current_shift.visa_sales += grand_total
        else:
            current_shift.cash_sales += grand_total

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
    """استرجاع خريطة حالة الـ 25 ترابيزة في الصالة (فاضية، مشغولة، طلبت الحساب، طلبت ويتر)."""
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
    """استرجاع تفاصيل الوردية المفتوحة حالياً."""
    shift = db.query(Shift).filter(Shift.status == "مفتوح").first()
    if not shift:
        return {"status": "no_active_shift", "message": "لا يوجد وردية مفتوحة حالياً"}

    # حساب المبيعات والمصروفات الحية المرتبطة بهذا الشيفت
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
    """فتح وردية جديدة."""
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
    """تقفيل الوردية الحالية وحساب العجز أو الزيادة."""
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
    """استرجاع سجل الورديات السابقة."""
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
    """تسجيل مصروف أو نثريات سريعة للوردية."""
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
    """استرجاع قائمة المصروفات."""
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


# ==========================================
# 5. واجهات خدمة الحجوزات (Reservations APIs)
# ==========================================

@app.get("/api/reservations")
@app.get("/api/cezar/reservations")
def get_reservations(db: Session = Depends(get_db)):
    """استرجاع قائمة الحجوزات."""
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
    """تسجيل حجز مسبق جديد."""
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


# ==========================================
# 6. واجهات خدمة قائمة الانتظار (Waiting List APIs)
# ==========================================

@app.get("/api/waiting-list")
@app.get("/api/cezar/waiting-list")
def get_waiting_list(db: Session = Depends(get_db)):
    """استرجاع قائمة الانتظار الحالية."""
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
    """إضافة زبون لقائمة الانتظار."""
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
    """تسكين العميل على طاولة متاحة وتحديث حالته."""
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
# 7. توليد باركود QR عالي الدقة لأي ترابيزة
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
# 8. نظام تسجيل دخول المدير وتغيير البيانات
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
        "manager_name": account.manager_name or "المدير العام"
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
# WSGI Compatibility (PythonAnywhere Support)
# ==========================================
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
except Exception:
    application = app
