"""
MediOrder - A simple medicine ordering web application.

Customers can browse a catalog of medicines, search by name or category,
add items to a cart, place an order with delivery details, and track
their order status using the order number.

Run with:
    pip install -r requirements.txt
    python app.py
"""

import os
import sqlite3
import uuid
from datetime import datetime

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "mediorder.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

ORDER_STATUSES = ["Pending", "Confirmed", "Out for Delivery", "Delivered", "Cancelled"]

SEED_MEDICINES = [
    # name, generic, category, description, price, stock, rx_required
    ("Napa 500mg", "Paracetamol", "Pain Relief", "Relieves fever, headache and mild pain.", 1.20, 500, 0),
    ("Ace 500mg", "Paracetamol", "Pain Relief", "Fast acting fever and pain reducer.", 1.10, 400, 0),
    ("Ibuprofen 400mg", "Ibuprofen", "Pain Relief", "Anti-inflammatory pain reliever for muscle and joint pain.", 2.50, 300, 0),
    ("Seclo 20mg", "Omeprazole", "Gastric", "Reduces stomach acid, treats gastric ulcers and acidity.", 5.00, 350, 0),
    ("Antacid Plus", "Aluminium Hydroxide", "Gastric", "Quick relief from heartburn and indigestion.", 3.00, 250, 0),
    ("Azithromycin 500mg", "Azithromycin", "Antibiotic", "Broad-spectrum antibiotic for bacterial infections.", 12.00, 150, 1),
    ("Amoxicillin 500mg", "Amoxicillin", "Antibiotic", "Antibiotic used for a wide range of infections.", 8.00, 200, 1),
    ("Ciprofloxacin 500mg", "Ciprofloxacin", "Antibiotic", "Treats urinary tract and other bacterial infections.", 10.00, 120, 1),
    ("Cetrizine 10mg", "Cetirizine", "Allergy", "Antihistamine for allergy, sneezing and runny nose.", 1.50, 450, 0),
    ("Loratadine 10mg", "Loratadine", "Allergy", "Non-drowsy relief from allergy symptoms.", 2.00, 300, 0),
    ("Vitamin C 500mg", "Ascorbic Acid", "Vitamins", "Boosts immunity and antioxidant support.", 4.00, 600, 0),
    ("Vitamin D3 2000IU", "Cholecalciferol", "Vitamins", "Supports bone health and immune function.", 6.50, 400, 0),
    ("Multivitamin Gold", "Multivitamin", "Vitamins", "Daily multivitamin and mineral supplement.", 9.00, 350, 0),
    ("Metformin 500mg", "Metformin", "Diabetes", "First-line medication for type 2 diabetes.", 3.50, 250, 1),
    ("Losartan 50mg", "Losartan Potassium", "Blood Pressure", "Controls high blood pressure.", 4.50, 220, 1),
    ("Amlodipine 5mg", "Amlodipine", "Blood Pressure", "Calcium channel blocker for hypertension.", 3.80, 240, 1),
    ("Salbutamol Inhaler", "Salbutamol", "Respiratory", "Quick relief inhaler for asthma symptoms.", 15.00, 100, 1),
    ("Cough Syrup 100ml", "Dextromethorphan", "Respiratory", "Soothes dry and irritating cough.", 5.50, 300, 0),
    ("ORS Sachet", "Oral Rehydration Salts", "First Aid", "Restores fluids and electrolytes during dehydration.", 0.80, 800, 0),
    ("Savlon Antiseptic 100ml", "Chlorhexidine", "First Aid", "Antiseptic liquid for cuts, wounds and cleaning.", 3.20, 350, 0),
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            generic TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            rx_required INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            note TEXT,
            payment_method TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            total REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            medicine_id INTEGER NOT NULL REFERENCES medicines(id),
            medicine_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL
        );
        """
    )
    count = db.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]
    if count == 0:
        db.executemany(
            "INSERT INTO medicines (name, generic, category, description, price, stock, rx_required)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            SEED_MEDICINES,
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Cart helpers (stored in the session as {medicine_id: quantity})
# ---------------------------------------------------------------------------

def get_cart():
    return session.setdefault("cart", {})


def cart_details():
    """Return (items, total) for the current session cart."""
    cart = get_cart()
    if not cart:
        return [], 0.0
    db = get_db()
    placeholders = ",".join("?" * len(cart))
    rows = db.execute(
        f"SELECT * FROM medicines WHERE id IN ({placeholders})", list(cart.keys())
    ).fetchall()
    items = []
    total = 0.0
    for row in rows:
        qty = cart[str(row["id"])]
        subtotal = row["price"] * qty
        total += subtotal
        items.append({"medicine": row, "quantity": qty, "subtotal": subtotal})
    items.sort(key=lambda i: i["medicine"]["name"].lower())
    return items, total


@app.context_processor
def inject_cart_count():
    return {"cart_count": sum(get_cart().values())}


# ---------------------------------------------------------------------------
# Customer routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    sql = "SELECT * FROM medicines WHERE 1=1"
    params = []
    if query:
        sql += " AND (name LIKE ? OR generic LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY name"

    medicines = db.execute(sql, params).fetchall()
    categories = [
        row["category"]
        for row in db.execute(
            "SELECT DISTINCT category FROM medicines ORDER BY category"
        ).fetchall()
    ]
    return render_template(
        "index.html",
        medicines=medicines,
        categories=categories,
        query=query,
        selected_category=category,
    )


@app.route("/cart/add/<int:medicine_id>", methods=["POST"])
def add_to_cart(medicine_id):
    db = get_db()
    medicine = db.execute(
        "SELECT * FROM medicines WHERE id = ?", (medicine_id,)
    ).fetchone()
    if medicine is None:
        flash("Medicine not found.", "error")
        return redirect(url_for("index"))

    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except ValueError:
        quantity = 1

    cart = get_cart()
    key = str(medicine_id)
    new_qty = cart.get(key, 0) + quantity
    if new_qty > medicine["stock"]:
        flash(f"Only {medicine['stock']} units of {medicine['name']} in stock.", "error")
        new_qty = medicine["stock"]
    if new_qty > 0:
        cart[key] = new_qty
        session.modified = True
        flash(f"{medicine['name']} added to cart.", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart")
def view_cart():
    items, total = cart_details()
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/update/<int:medicine_id>", methods=["POST"])
def update_cart(medicine_id):
    cart = get_cart()
    key = str(medicine_id)
    if key in cart:
        try:
            quantity = int(request.form.get("quantity", 1))
        except ValueError:
            quantity = 1
        if quantity <= 0:
            cart.pop(key)
        else:
            db = get_db()
            medicine = db.execute(
                "SELECT stock, name FROM medicines WHERE id = ?", (medicine_id,)
            ).fetchone()
            if medicine and quantity > medicine["stock"]:
                quantity = medicine["stock"]
                flash(f"Only {medicine['stock']} units of {medicine['name']} in stock.", "error")
            cart[key] = quantity
        session.modified = True
    return redirect(url_for("view_cart"))


@app.route("/cart/remove/<int:medicine_id>", methods=["POST"])
def remove_from_cart(medicine_id):
    cart = get_cart()
    if cart.pop(str(medicine_id), None) is not None:
        session.modified = True
        flash("Item removed from cart.", "success")
    return redirect(url_for("view_cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = cart_details()
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("index"))

    rx_items = [i for i in items if i["medicine"]["rx_required"]]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        note = request.form.get("note", "").strip()
        payment_method = request.form.get("payment_method", "Cash on Delivery")
        rx_confirmed = request.form.get("rx_confirmed")

        errors = []
        if not name:
            errors.append("Name is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not address:
            errors.append("Delivery address is required.")
        if rx_items and not rx_confirmed:
            errors.append(
                "Please confirm you hold a valid prescription for the "
                "prescription-only items in your cart."
            )

        db = get_db()
        # Re-validate stock at order time.
        for item in items:
            current = db.execute(
                "SELECT stock FROM medicines WHERE id = ?",
                (item["medicine"]["id"],),
            ).fetchone()
            if current is None or current["stock"] < item["quantity"]:
                errors.append(
                    f"Insufficient stock for {item['medicine']['name']}. "
                    "Please update your cart."
                )

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "checkout.html", items=items, total=total, rx_items=rx_items,
                form=request.form,
            )

        order_number = "MO-" + uuid.uuid4().hex[:8].upper()
        cursor = db.execute(
            "INSERT INTO orders (order_number, customer_name, phone, address, note,"
            " payment_method, status, total, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?, ?)",
            (
                order_number,
                name,
                phone,
                address,
                note,
                payment_method,
                total,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        order_id = cursor.lastrowid
        for item in items:
            db.execute(
                "INSERT INTO order_items (order_id, medicine_id, medicine_name,"
                " quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                (
                    order_id,
                    item["medicine"]["id"],
                    item["medicine"]["name"],
                    item["quantity"],
                    item["medicine"]["price"],
                ),
            )
            db.execute(
                "UPDATE medicines SET stock = stock - ? WHERE id = ?",
                (item["quantity"], item["medicine"]["id"]),
            )
        db.commit()

        session["cart"] = {}
        return redirect(url_for("order_confirmation", order_number=order_number))

    return render_template(
        "checkout.html", items=items, total=total, rx_items=rx_items, form={},
    )


@app.route("/order/<order_number>")
def order_confirmation(order_number):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE order_number = ?", (order_number,)
    ).fetchone()
    if order is None:
        flash("Order not found.", "error")
        return redirect(url_for("track_order"))
    items = db.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order["id"],)
    ).fetchall()
    return render_template("order.html", order=order, items=items)


@app.route("/track", methods=["GET", "POST"])
def track_order():
    if request.method == "POST":
        order_number = request.form.get("order_number", "").strip().upper()
        db = get_db()
        order = db.execute(
            "SELECT * FROM orders WHERE order_number = ?", (order_number,)
        ).fetchone()
        if order is None:
            flash("No order found with that order number.", "error")
            return render_template("track.html")
        return redirect(url_for("order_confirmation", order_number=order_number))
    return render_template("track.html")


# ---------------------------------------------------------------------------
# Admin routes (simple, unauthenticated demo admin)
# ---------------------------------------------------------------------------

@app.route("/admin/orders")
def admin_orders():
    db = get_db()
    orders = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template("admin_orders.html", orders=orders, statuses=ORDER_STATUSES)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
def admin_update_status(order_id):
    status = request.form.get("status")
    if status not in ORDER_STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("admin_orders"))
    db = get_db()
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    db.commit()
    flash("Order status updated.", "success")
    return redirect(url_for("admin_orders"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
