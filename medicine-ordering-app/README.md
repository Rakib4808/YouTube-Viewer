# MediOrder — Medicine Ordering App

A simple web application where customers can order medicines online, built with
Flask and SQLite (no external database required).

## Features

- **Browse catalog** — 20 seeded medicines across categories (Pain Relief,
  Antibiotic, Gastric, Allergy, Vitamins, Diabetes, Blood Pressure,
  Respiratory, First Aid)
- **Search & filter** — search by brand or generic name, filter by category
- **Shopping cart** — add, update quantity, and remove items (session-based)
- **Stock awareness** — quantities are capped at available stock, and stock is
  re-validated and decremented when an order is placed
- **Prescription handling** — prescription-only (Rx) items are flagged, and
  checkout requires the customer to confirm they hold a valid prescription
- **Checkout** — name, phone, delivery address, optional note, and payment
  method (cash/card on delivery)
- **Order tracking** — every order gets a unique order number (e.g.
  `MO-1A2B3C4D`) the customer can use on the Track Order page
- **Admin panel** — view all orders and update their status
  (Pending → Confirmed → Out for Delivery → Delivered / Cancelled)

## Getting started

```bash
cd medicine-ordering-app
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.

The SQLite database (`mediorder.db`) is created and seeded with sample
medicines automatically on first run. Delete the file to reset the data.

## Project structure

```
medicine-ordering-app/
├── app.py               # Flask app: routes, database, cart, and order logic
├── requirements.txt
├── static/
│   └── style.css
└── templates/
    ├── base.html        # Shared layout (navbar, flash messages, footer)
    ├── index.html       # Catalog with search and category filter
    ├── cart.html        # Shopping cart
    ├── checkout.html    # Delivery details + order summary
    ├── order.html       # Order confirmation / details
    ├── track.html       # Track order by order number
    └── admin_orders.html# Admin: list orders and update status
```

## Notes for production use

This is a demo starting point. Before real-world use you would need, at
minimum: user accounts and authentication (especially for `/admin`),
real prescription upload and pharmacist verification, a payment gateway,
CSRF protection, and a production WSGI server (e.g. gunicorn) instead of
the Flask dev server.
