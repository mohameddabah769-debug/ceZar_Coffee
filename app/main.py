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
from sqlalchemy import desc, func

from .database import engine, Base, SessionLocal, get_db
from .models import MenuItem, TableOrder, ManagerAccount
from .seed import seed_menu

# إنشاء الجداول وتحميل المنيو وحساب المدير
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_menu(db)
    if db.query(ManagerAccount).count() == 0:
        db.add(ManagerAccount(username="admin", password="123", manager_name="مدير سيزر كوفي"))
        db.commit()

app = FastAPI(
    title="ceZar COFFEE - Smart QR & Management System",
    description="نظام إدارة المنيو والطلبات الذكي لكافيه سيزر كوفي - م/ محمد دباح (01095744676)",
    version="1.0.0"
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
# 3. واجهات برمجة الطلبات (Order APIs)
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

    order = TableOrder(
        table_number=order_data.table_number,
        items_summary=items_summary,
        total_price=total,
        customer_name=order_data.customer_name or f"ترابيزة {order_data.table_number}",
        customer_phone=order_data.customer_phone or "",
        notes=order_data.notes or "",
        status="جديد"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "status": "success",
        "message": f"تم استلام طلب ترابيزة {order.table_number} بنجاح!",
        "order_id": order.id,
        "table_number": order.table_number,
        "total_price": order.total_price
    }


@app.get("/api/orders")
@app.get("/api/cezar/orders")
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(TableOrder).order_by(desc(TableOrder.created_at)).limit(100).all()

    total_orders = db.query(TableOrder).count()
    delivered_count = db.query(TableOrder).filter(TableOrder.status.in_(["تم التقديم", "تمت التسوية"])).count()
    pending_count = db.query(TableOrder).filter(TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير", "نداء ويتر"]) | TableOrder.status.like("طلب حساب%")).count()
    # تجنب احتساب مبيعات طلب الحساب مرتين (نحسب فقط أوردرات الأطعمة والمشروبات الفعلية غير الملغية)
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
                "table_number": o.table_number,
                "items_summary": o.items_summary,
                "total_price": o.total_price,
                "status": o.status,
                "customer_name": o.customer_name,
                "customer_phone": o.customer_phone,
                "notes": o.notes,
                "created_at": o.created_at.strftime("%I:%M %p") if o.created_at else ""
            }
            for o in orders
        ]
    }


@app.get("/api/tables/{table_number}/bill")
@app.get("/api/cezar/tables/{table_number}/bill")
def get_table_bill(table_number: int, db: Session = Depends(get_db)):
    """استرجاع كشف الحساب والطلبات الحالية لترابيزة معينة."""
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


@app.post("/api/orders/{order_id}/status")
@app.post("/api/cezar/orders/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(TableOrder).filter(TableOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    # إذا كانت التسوية لطلب حساب، نحدث حالة أوردرات الترابيزة لـ "تم التقديم" لغلق الحساب
    if order.status in ["تم التقديم", "تمت التسوية"] and (order.items_summary and "طلب الحساب" in order.items_summary):
        db.query(TableOrder).filter(
            TableOrder.table_number == order.table_number,
            TableOrder.status.in_(["جديد", "جاري التحضير", "قيد التحضير"])
        ).update({"status": "تم التقديم"}, synchronize_session=False)

    db.commit()
    return {"status": "success", "order_id": order.id, "new_status": order.status}


@app.post("/api/orders/call-waiter")
@app.post("/api/cezar/orders/call-waiter")
def call_waiter_endpoint(req: CallWaiterRequest, db: Session = Depends(get_db)):
    """طلب نداء الويتر من الترابيزة مباشرة إلى لوحة المدير."""
    order = TableOrder(
        table_number=req.table_number,
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
    """طلب الحساب من الترابيزة مربوطاً بطلباتها الفعلية وإجمالي المبلغ."""
    method = req.payment_method if req.payment_method in ["كاش", "فيزا"] else "كاش"
    icon = "💵" if method == "كاش" else "💳"

    # جلب جميع أوردرات الترابيزة النشطة لحساب الإجمالي
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
        orders_details = []
        for o in active_orders:
            orders_details.append(o.items_summary)
        items_text = "\n".join(orders_details)
        summary = f"🧾 طلب الحساب النهائي ({method}) {icon}\n💰 الإجمالي المطلوب تحصيله: {total_bill:g} جنيه\n📋 الطلبات:\n{items_text}"
    else:
        summary = f"🧾 طلب الحساب النهائي ({method}) {icon} (طلب حساب مباشر بدون أوردرات مسبقة)"

    order = TableOrder(
        table_number=req.table_number,
        items_summary=summary,
        total_price=total_bill,
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
    """تصفير جميع الطلبات التجريبية وبدء وردية جديدة."""
    db.query(TableOrder).delete()
    db.commit()
    return {"status": "success", "message": "تم تصفير جميع الطلبات وبدء وردية جديدة بنجاح!"}


# ==========================================
# 4. توليد باركود QR عالي الدقة لأي ترابيزة
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
# 5. نظام تسجيل دخول المدير وتغيير البيانات
# ==========================================

@app.post("/api/auth/login")
@app.post("/api/cezar/auth/login")
def manager_login(data: LoginRequest, db: Session = Depends(get_db)):
    """تسجيل دخول المدير باسم مستخدم وكلمة مرور."""
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
    """تغيير اسم المستخدم وكلمة المرور للمدير."""
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

