import sys

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from sqlalchemy.orm import Session
try:
    from .models import MenuItem, InventoryItem, PromoCode, ManagerAccount, MenuItemRecipe, Employee, SalaryPayment, CafeSetting, CafeTableConfig
except ImportError:
    from models import MenuItem, InventoryItem, PromoCode, ManagerAccount, MenuItemRecipe, Employee, SalaryPayment, CafeSetting, CafeTableConfig

DEFAULT_STAFF_USERS = [
    {"username": "admin", "password": "0000", "manager_name": "المدير العام (ceZar)", "role": "admin"},
    {"username": "cashier", "password": "1234", "manager_name": "كاشير الصالة السريع", "role": "cashier"},
    {"username": "barista", "password": "1234", "manager_name": "باريستا البار الرئيسي", "role": "barista"},
]

DEFAULT_EMPLOYEES = [
    {"name": "كريم أحمد", "role": "رئيس باريستا", "phone": "01011223344", "salary": 6000.0, "hire_date": "2025-01-10", "status": "نشط"},
    {"name": "محمود سامح", "role": "كاشير رئيسي", "phone": "01122334455", "salary": 4500.0, "hire_date": "2025-02-01", "status": "نشط"},
    {"name": "عمر خالد", "role": "كابتن صالة وويتر", "phone": "01233445566", "salary": 3800.0, "hire_date": "2025-03-15", "status": "نشط"},
    {"name": "يوسف إبراهيم", "role": "باريستا مساعد", "phone": "01544556677", "salary": 4000.0, "hire_date": "2025-04-01", "status": "نشط"},
]

CEZAR_MENU_DATA = [
    # 0. الكوفى (Hot Coffee)
    {"category": "الكوفى", "name": "اسبريسو سنجل", "price": 35, "description": "شوت إسبريسو نقي ومركز"},
    {"category": "الكوفى", "name": "اسبريسو دبل", "price": 55, "description": "دبل شوت إسبريسو لتركيز وطاقة أعلى"},
    {"category": "الكوفى", "name": "اسبريسو ميكاتو", "price": 60, "description": "إسبريسو مع لمسة رغوة حليب ناعمة"},
    {"category": "الكوفى", "name": "اسبريسو فلات وايت", "price": 60, "description": "إسبريسو دبل مع حليب مبخر كريمي"},
    {"category": "الكوفى", "name": "اسبريسو كراميل ميكاتو", "price": 60, "description": "إسبريسو مع حليب وصوص كراميل ذهبي"},
    {"category": "الكوفى", "name": "اسبريسو كورتادو", "price": 60, "description": "إسبريسو مع حليب مبخر بنسب متساوية"},
    {"category": "الكوفى", "name": "قهوة تركى سنجل", "price": 35, "description": "قهوة تركي ببن سيزر الفاخر والمحبب"},
    {"category": "الكوفى", "name": "قهوة تركى دبل", "price": 50, "description": "فنجان قهوة تركي دبل لمزاج عالي"},
    {"category": "الكوفى", "name": "قهوة فرنساوى", "price": 50, "description": "قهوة باللبن المبخر الناعم"},
    {"category": "الكوفى", "name": "قهوة فليفر", "price": 55, "description": "قهوة تركي بنكهات (بندق / فانيليا / كراميل)"},
    {"category": "الكوفى", "name": "نسكافية بلاك", "price": 40, "description": "نسكافيه كلاسيك ساخن وسادة"},
    {"category": "الكوفى", "name": "نسكافية حليب", "price": 55, "description": "نسكافيه ممزوج بالحليب الساخن"},
    {"category": "الكوفى", "name": "نسكافية فليفر", "price": 60, "description": "نسكافيه بحليب ونكهة (فانيليا / كراميل / بندق)"},
    {"category": "الكوفى", "name": "لاتيه كلاسيك", "price": 65, "description": "قهوة بالحليب ورغوة ناعمة"},
    {"category": "الكوفى", "name": "لاتيه فليفر", "price": 70, "description": "لاتيه ساخن بنكهتك المفضلة"},
    {"category": "الكوفى", "name": "كابتشينو كلاسيك", "price": 60, "description": "كابتشينو إيطالي غني بالرغوة ورشة كاكاو"},
    {"category": "الكوفى", "name": "كابتشينو فليفر", "price": 65, "description": "كابتشينو بنكهة كراميل أو فانيليا أو بندق"},
    {"category": "الكوفى", "name": "موكا", "price": 65, "description": "مزيج الإسبريسو مع الشوكولاتة والحليب الساخن"},
    {"category": "الكوفى", "name": "امريكان كوفى", "price": 60, "description": "قهوة أمريكان ساخنة ومفلترة على أصولها"},

    # 00. مشروبات ساخنة
    {"category": "مشروبات ساخنة", "name": "شاى", "price": 20, "description": "شاي مصري بالنعناع أو سادة"},
    {"category": "مشروبات ساخنة", "name": "شاى كرك", "price": 30, "description": "شاي هندي مبهر بالحليب والهيل والزعفران"},
    {"category": "مشروبات ساخنة", "name": "شاى حليب", "price": 40, "description": "شاي بحليب ساخن كامل الدسم"},
    {"category": "مشروبات ساخنة", "name": "شاى نكهات", "price": 25, "description": "شاي بنكهات خوخ / توت / ليمون"},
    {"category": "مشروبات ساخنة", "name": "أعشاب", "price": 25, "description": "يانسون / كركديه / نعناع / تليو / بابونج"},
    {"category": "مشروبات ساخنة", "name": "ميكس اعشاب", "price": 40, "description": "توليفة أعشاب مهدئة ومريحة"},
    {"category": "مشروبات ساخنة", "name": "ليمون عسل", "price": 30, "description": "ليمون دافئ محلى بعسل النحل الطبيعي"},
    {"category": "مشروبات ساخنة", "name": "سحلب مكسرات", "price": 55, "description": "سحلب بلبن وقشطة ومكسرات محمصة وقرفة"},
    {"category": "مشروبات ساخنة", "name": "سحلب فواكه", "price": 65, "description": "سحلب ساخن غني بقطع الفواكه الطازجة"},
    {"category": "مشروبات ساخنة", "name": "سحلب شوكليت", "price": 55, "description": "سحلب ساخن مع صوص شوكولاتة فاخر"},
    {"category": "مشروبات ساخنة", "name": "هوت شوكليت", "price": 60, "description": "شوكولاتة ساخنة غنية وكريمية"},
    {"category": "مشروبات ساخنة", "name": "هوت اوريو", "price": 70, "description": "مشروب الأوريو الساخن بالشوكولاتة والكريمة"},
    {"category": "مشروبات ساخنة", "name": "هوت بوريو", "price": 65, "description": "بوريو ساخن مع الحليب والشوكولاتة الذائبة"},
    {"category": "مشروبات ساخنة", "name": "هوت كيت كات", "price": 75, "description": "شوكولاتة كيت كات المذابة مع الحليب الدافئ"},
    {"category": "مشروبات ساخنة", "name": "هوت هوهوز", "price": 60, "description": "هوهوز ساخن غرقان في الحليب والشوكولاتة"},
    {"category": "مشروبات ساخنة", "name": "ابل سيدر", "price": 50, "description": "عصير تفاح ساخن مع أعواد القرفة والقرنفل"},

    # 1. أيس كوفي
    {"category": "أيس كوفي", "name": "أيس لاتيه كلاسيك", "price": 65, "description": "إسبريسو مع حليب بارد وثلج"},
    {"category": "أيس كوفي", "name": "أيس لاتيه فليفر", "price": 70, "description": "أيس لاتيه بنكهة فانيليا أو كراميل أو بندق"},
    {"category": "أيس كوفي", "name": "سبانش لاتيه بارد", "price": 75, "description": "إسبريسو مع حليب مكثف محلى وحليب بارد"},
    {"category": "أيس كوفي", "name": "أيس موكا شوكليت", "price": 70, "description": "إسبريسو مع صوص شوكولاتة وحليب وثلج"},
    {"category": "أيس كوفي", "name": "أيس وايت موكا", "price": 75, "description": "إسبريسو مع صوص شوكولاتة بيضاء وحليب بارد"},
    {"category": "أيس كوفي", "name": "أيس امريكانو", "price": 50, "description": "شوت إسبريسو مزدوج مع ماء مثلج ومنعش"},

    # 2. ميلك شيك
    {"category": "ميلك شيك", "name": "ميلك شيك فانيليا", "price": 65, "description": "أيس كريم فانيليا مع حليب وكريمة مخفوقة"},
    {"category": "ميلك شيك", "name": "ميلك شيك شوكولاتة", "price": 65, "description": "أيس كريم شوكولاتة مع صوص فادج غني"},
    {"category": "ميلك شيك", "name": "ميلك شيك فراولة", "price": 65, "description": "أيس كريم فراولة طبيعية مع صوص فراولة"},
    {"category": "ميلك شيك", "name": "ميلك شيك أوريو", "price": 75, "description": "بسكويت أوريو مطحون مع أيس كريم وشوكولاتة"},
    {"category": "ميلك شيك", "name": "ميلك شيك لوتس", "price": 80, "description": "بسكويت لوتس وزبدة لوتس أصلية مع الكريمة"},
    {"category": "ميلك شيك", "name": "ميلك شيك كيت كات", "price": 80, "description": "أصابع كيت كات مع أيس كريم وكريمة"},

    # 3. ميكسات فريش وموهيتو
    {"category": "ميكسات فريش", "name": "موهيتو كلاسيك نعناع", "price": 55, "description": "سفن أب مع ليمون ونعناع فريش وثلج مجروش"},
    {"category": "ميكسات فريش", "name": "موهيتو بلوبيري (توت أزرق)", "price": 60, "description": "موهيتو منعش مع سيرب توت أزرق"},
    {"category": "ميكسات فريش", "name": "موهيتو فراولة", "price": 60, "description": "موهيتو مع قطع فراولة وسيرب فراولة مركز"},
    {"category": "ميكسات فريش", "name": "موهيتو بطيخ", "price": 60, "description": "موهيتو بنكهة البطيخ المنعشة للصيف"},
    {"category": "ميكسات فريش", "name": "ريد بول بطيخ / توت", "price": 75, "description": "مشروب الطاقة ريد بول مع نكهتك المفضلة وثلج"},
    {"category": "ميكسات فريش", "name": "سموذي مانجو فريش", "price": 60, "description": "مانجو طبيعية مثلجة وسميكة"},
    {"category": "ميكسات فريش", "name": "سموذي فراولة فريش", "price": 60, "description": "فراولة بيوريه مثلجة ومنعشة"},
    {"category": "ميكسات فريش", "name": "عصير برتقال فريش", "price": 45, "description": "برتقال طبيعي 100% معصور فريش"},
    {"category": "ميكسات فريش", "name": "ليمون نعناع فريش", "price": 40, "description": "عصير ليمون ونعناع مثلج ومنعش"},

    # 4. الحلويات والوافلز
    {"category": "وافلز", "name": "وافل نوتيلا كلاسيك", "price": 75, "description": "وافل بلجيكي مقرمش غرقان نوتيلا أصلية"},
    {"category": "وافلز", "name": "وافل لوتس بلجيكي", "price": 85, "description": "وافل بزبدة وبسكويت لوتس مقرمش"},
    {"category": "وافلز", "name": "وافل ميكس شوكليت (أبيض وبني)", "price": 85, "description": "وافل بنوتيلا وشوكولاتة بلجيكية بيضاء"},
    {"category": "وافلز", "name": "وافل فواكه نوتيلا", "price": 95, "description": "وافل نوتيلا مع قطع موز وفراولة طازجة"},
    {"category": "وافلز", "name": "كريب نوتيلا بالموز", "price": 80, "description": "كريب فرنسي طري محشو نوتيلا وموز ومكسرات"},
    {"category": "وافلز", "name": "بان كيك ميني شوكولاتة", "price": 70, "description": "قطع ميني بان كيك هشة مع صوص شوكولاتة"},
    {"category": "وافلز", "name": "أم علي بالمكسرات والقشطة", "price": 65, "description": "أم علي ساخنة باللبن والقشطة الفلاحي والمكسرات"},
    {"category": "وافلز", "name": "مولتن كيك فادج", "price": 85, "description": "كيك شوكولاتة ساخن محشو لافا ذائبة مع بولة أيس كريم"},
    {"category": "وافلز", "name": "تشيز كيك بلوبيري", "price": 75, "description": "تشيز كيك كريمي مع صوص التوت الأزرق الفاخر"},

    # 5. شيشة
    {"category": "شيشة", "name": "شيشة سلوم", "price": 40, "description": "شيشة سلوم مصرية على أصولها"},
    {"category": "شيشة", "name": "شيشة قص", "price": 45, "description": "معسل قص أصلي ومظبوط"},
    {"category": "شيشة", "name": "شيشة فاخر", "price": 70, "description": "معسل فاخر بنكهات التفاحتين، عنب، خوخ، بطيخ"},
    {"category": "شيشة", "name": "شيشة فاخر ميكس", "price": 85, "description": "ميكس نكهات فاخرة حسب اختيارك"}
]

DEFAULT_INVENTORY = [
    {"name": "بن إسبريسو كولومبي فاخر", "unit": "كجم", "current_stock": 18.5, "min_alert_stock": 5.0, "cost_per_unit": 450.0},
    {"name": "بن تركي سيزر خصوصي", "unit": "كجم", "current_stock": 12.0, "min_alert_stock": 4.0, "cost_per_unit": 380.0},
    {"name": "حليب كامل الدسم مبخر", "unit": "لتر", "current_stock": 42.0, "min_alert_stock": 10.0, "cost_per_unit": 38.0},
    {"name": "سكر أبيض ناعم", "unit": "كجم", "current_stock": 25.0, "min_alert_stock": 8.0, "cost_per_unit": 35.0},
    {"name": "شوكولاتة نوتيلا أصلية", "unit": "علبة", "current_stock": 6.0, "min_alert_stock": 2.0, "cost_per_unit": 280.0},
    {"name": "زبدة وبسكويت لوتس", "unit": "علبة", "current_stock": 4.0, "min_alert_stock": 2.0, "cost_per_unit": 220.0},
    {"name": "سيرب فانيليا وبندق وكراميل", "unit": "زجاجة", "current_stock": 8.0, "min_alert_stock": 3.0, "cost_per_unit": 180.0},
    {"name": "أكواب تيك أواي 12oz بغطاء", "unit": "كرتونة", "current_stock": 5.0, "min_alert_stock": 2.0, "cost_per_unit": 350.0},
    {"name": "مناديل وشاليموه كافيه", "unit": "باكت", "current_stock": 15.0, "min_alert_stock": 4.0, "cost_per_unit": 90.0},
    {"name": "علب مشروب الطاقة ريد بول", "unit": "علبة", "current_stock": 24.0, "min_alert_stock": 6.0, "cost_per_unit": 45.0},
]

DEFAULT_PROMO_CODES = [
    {"code": "CEZAR10", "discount_type": "percentage", "discount_value": 10.0, "min_order_value": 50.0},
    {"code": "WELCOME", "discount_type": "percentage", "discount_value": 15.0, "min_order_value": 70.0},
    {"code": "VIP", "discount_type": "percentage", "discount_value": 20.0, "min_order_value": 100.0},
    {"code": "COFFEE20", "discount_type": "fixed", "discount_value": 20.0, "min_order_value": 80.0},
]


def seed_menu(db: Session):
    count = db.query(MenuItem).count()
    if count == 0:
        for item in CEZAR_MENU_DATA:
            db_item = MenuItem(
                category=item["category"],
                name=item["name"],
                price=float(item["price"]),
                description=item.get("description"),
                is_available=True
            )
            db.add(db_item)
        db.commit()

    # Seed Inventory
    if db.query(InventoryItem).count() == 0:
        for inv in DEFAULT_INVENTORY:
            db.add(InventoryItem(
                name=inv["name"],
                unit=inv["unit"],
                current_stock=inv["current_stock"],
                min_alert_stock=inv["min_alert_stock"],
                cost_per_unit=inv["cost_per_unit"]
            ))
        db.commit()

    # Seed Promo Codes
    if db.query(PromoCode).count() == 0:
        for p in DEFAULT_PROMO_CODES:
            db.add(PromoCode(
                code=p["code"],
                discount_type=p["discount_type"],
                discount_value=p["discount_value"],
                min_order_value=p["min_order_value"],
                is_active=True
            ))
        db.commit()

    # Seed Default Staff Roles & Permissions
    for staff in DEFAULT_STAFF_USERS:
        existing = db.query(ManagerAccount).filter(ManagerAccount.username == staff["username"]).first()
        if not existing:
            db.add(ManagerAccount(
                username=staff["username"],
                password=staff["password"],
                manager_name=staff["manager_name"],
                role=staff["role"]
            ))
        else:
            if not existing.role:
                existing.role = staff["role"]
    db.commit()

    # Update cost_price for existing menu items if 0
    items_without_cost = db.query(MenuItem).filter((MenuItem.cost_price == None) | (MenuItem.cost_price == 0)).all()
    for item in items_without_cost:
        item.cost_price = round(item.price * 0.32, 2)  # 32% food cost standard
    if items_without_cost:
        db.commit()

    # Seed Employees (شؤون الموظفين)
    if db.query(Employee).count() == 0:
        for emp in DEFAULT_EMPLOYEES:
            db.add(Employee(
                name=emp["name"],
                role=emp["role"],
                phone=emp["phone"],
                salary=emp["salary"],
                hire_date=emp["hire_date"],
                status=emp["status"]
            ))
        db.commit()

    # Seed Sample Salary Payment if none
    if db.query(SalaryPayment).count() == 0:
        first_emp = db.query(Employee).first()
        if first_emp:
            db.add(SalaryPayment(
                employee_id=first_emp.id,
                amount=first_emp.salary,
                payment_type="راتب شهري",
                month="2026-11",
                notes="صرف راتب شهر نوفمبر 2026"
            ))
            db.commit()

    # Seed Cafe Settings (إعدادات وهوية الكافيه الشاملة)
    default_settings = {
        "cafe_name_ar": "كافيه سيزر",
        "cafe_name_en": "ceZar COFFEE",
        "cafe_tagline": "Specialty Coffee & Roastery",
        "cafe_phone": "01023456789",
        "cafe_whatsapp": "01023456789",
        "cafe_address": "شارع الجمهورية - وسط البلد",
        "wifi_ssid": "ceZar_Coffee_5G",
        "wifi_password": "cezar_coffee_vip",
        "currency": "ج.م",
        "tax_rate": "0",
        "tax_enabled": "false",
        "service_charge": "0",
        "service_charge_enabled": "false",
        "default_delivery_fee": "20",
        "min_order_value": "50",
        "receipt_header": "ceZar COFFEE - أهلاً وسهلاً بكم",
        "receipt_footer": "شكراً لزيارتكم كافيه سيزر - نتشرف بكم دائماً ☕",
        "receipt_show_wifi": "true",
        "tables_count": "25",
        "sound_alerts_enabled": "true",
        "operating_hours": "08:00 AM - 02:00 AM",
        "manager_void_pin": "1234"
    }
    for k, v in default_settings.items():
        if not db.query(CafeSetting).filter(CafeSetting.key == k).first():
            db.add(CafeSetting(key=k, value=str(v), description="إعداد النظام الافتراضي"))
    db.commit()

    seed_recipes(db)

    # Seed 25 Table Configs
    if db.query(CafeTableConfig).count() == 0:
        for t in range(1, 26):
            if t <= 10:
                zone = "صالة رئيسية"
                cap = 4
            elif t <= 18:
                zone = "تراس خارجي"
                cap = 4
            elif t <= 22:
                zone = "ركن عائلي"
                cap = 6
            else:
                zone = "ركن VIP"
                cap = 8
            db.add(CafeTableConfig(table_number=t, capacity=cap, zone=zone, is_active=True))
        db.commit()



def seed_recipes(db: Session):
    """ربط المشروبات الأساسية بمقادير الخامات والجرامات لحساب التكلفة والخصم الآلي."""
    try:
        if db.query(MenuItemRecipe).count() > 0:
            return
        
        inv_items = {i.name: i for i in db.query(InventoryItem).all()}
        espresso_beans = next((v for k, v in inv_items.items() if "إسبريسو" in k or "اسبريسو" in k), None)
        turkish_beans = next((v for k, v in inv_items.items() if "تركي" in k or "تركى" in k), None)
        milk = next((v for k, v in inv_items.items() if "حليب" in k or "لبن" in k), None)
        syrup = next((v for k, v in inv_items.items() if "سيرب" in k), None)

        recipe_map = [
            ("اسبريسو سنجل", [(espresso_beans, 0.018)]),
            ("اسبريسو دبل", [(espresso_beans, 0.036)]),
            ("اسبريسو ميكاتو", [(espresso_beans, 0.018), (milk, 0.05)]),
            ("اسبريسو فلات وايت", [(espresso_beans, 0.020), (milk, 0.15)]),
            ("اسبريسو كورتادو", [(espresso_beans, 0.018), (milk, 0.08)]),
            ("اسبريسو كراميل ميكاتو", [(espresso_beans, 0.018), (milk, 0.18), (syrup, 0.02)]),
            ("لاتيه كلاسيك", [(espresso_beans, 0.018), (milk, 0.20)]),
            ("لاتيه فليفر", [(espresso_beans, 0.018), (milk, 0.20), (syrup, 0.02)]),
            ("كابتشينو كلاسيك", [(espresso_beans, 0.018), (milk, 0.16)]),
            ("كابتشينو فليفر", [(espresso_beans, 0.018), (milk, 0.16), (syrup, 0.02)]),
            ("موكا", [(espresso_beans, 0.018), (milk, 0.18)]),
            ("امريكان كوفى", [(espresso_beans, 0.018)]),
            ("قهوة تركى سنجل", [(turkish_beans, 0.012)]),
            ("قهوة تركى دبل", [(turkish_beans, 0.024)]),
            ("قهوة فرنساوى", [(turkish_beans, 0.012), (milk, 0.15)]),
        ]

        for item_name, ingredients in recipe_map:
            m_item = db.query(MenuItem).filter(MenuItem.name == item_name).first()
            if not m_item:
                continue
            total_cost = 0.0
            for inv_obj, amount in ingredients:
                if inv_obj:
                    db.add(MenuItemRecipe(menu_item_id=m_item.id, inventory_item_id=inv_obj.id, amount_used=amount))
                    total_cost += amount * (inv_obj.cost_per_unit or 0.0)
            if total_cost > 0:
                m_item.cost_price = round(total_cost, 2)
        
        db.commit()
    except Exception as e:
        print(f"Error seeding recipes: {e}")
