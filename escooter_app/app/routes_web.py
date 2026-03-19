from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import PaymentMethod, Rental, Vehicle, VehicleType
from .services import finish_rental, start_rental


main_bp = Blueprint("main", __name__)


def role_required(expected_role: str):
    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            if current_user.role != expected_role:
                flash("Für diese Seite fehlt die passende Rolle.", "danger")
                return redirect(url_for("main.dashboard"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def parse_vehicle_form(form):
    vehicle_code = form.get("vehicle_code", "").strip()
    qr_code = form.get("qr_code", "").strip()
    status = form.get("status", "available").strip()

    if not vehicle_code:
        raise ValueError("Fahrzeug-Code fehlt. Beispiel: SC-3001")
    if not qr_code:
        raise ValueError("QR-Code fehlt. Beispiel: QR-SC-3001")

    try:
        vehicle_type_id = int(form.get("vehicle_type_id", "0"))
    except ValueError as exc:
        raise ValueError("Der Fahrzeug-Typ ist ungültig.") from exc

    try:
        battery_level = int(form.get("battery_level", ""))
    except ValueError as exc:
        raise ValueError("Der Akku muss eine ganze Zahl zwischen 0 und 100 sein.") from exc

    if battery_level < 0 or battery_level > 100:
        raise ValueError("Der Akku muss zwischen 0 und 100 liegen.")

    try:
        latitude = Decimal(form.get("latitude", "").strip())
        longitude = Decimal(form.get("longitude", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Latitude und Longitude müssen gültige Zahlen sein. Beispiel: 46.948090 und 7.447440") from exc

    if latitude < Decimal("-90") or latitude > Decimal("90"):
        raise ValueError("Latitude muss zwischen -90 und 90 liegen.")

    if longitude < Decimal("-180") or longitude > Decimal("180"):
        raise ValueError("Longitude muss zwischen -180 und 180 liegen.")

    if status not in ["available", "maintenance", "inactive"]:
        raise ValueError("Der Status ist ungültig.")

    return {
        "vehicle_code": vehicle_code,
        "qr_code": qr_code,
        "vehicle_type_id": vehicle_type_id,
        "battery_level": battery_level,
        "latitude": latitude,
        "longitude": longitude,
        "status": status,
    }


@main_bp.route("/")
def index():
    available_count = Vehicle.query.filter_by(status="available", is_active=True).count()
    active_rentals = Rental.query.filter_by(status="active").count()
    return render_template("index.html", available_count=available_count, active_rentals=active_rentals)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    my_active_rental = None
    my_vehicles = []
    available_vehicles = []
    payment_methods = []
    my_payments = []

    if current_user.role == "provider":
        my_vehicles = Vehicle.query.filter_by(owner_id=current_user.id).order_by(Vehicle.id.desc()).all()
    else:
        my_active_rental = Rental.query.filter_by(user_id=current_user.id, status="active").first()
        available_vehicles = Vehicle.query.filter_by(status="available", is_active=True).order_by(Vehicle.id.asc()).all()
        payment_methods = PaymentMethod.query.filter_by(user_id=current_user.id).all()
        my_payments = current_user.rentals

    return render_template(
        "dashboard.html",
        my_vehicles=my_vehicles,
        available_vehicles=available_vehicles,
        my_active_rental=my_active_rental,
        payment_methods=payment_methods,
        my_payments=my_payments,
    )


@main_bp.route("/provider/vehicles/new", methods=["GET", "POST"])
@login_required
@role_required("provider")
def create_vehicle():
    vehicle_types = VehicleType.query.filter_by(is_active=True).all()
    if request.method == "POST":
        try:
            data = parse_vehicle_form(request.form)

            existing_code = Vehicle.query.filter_by(vehicle_code=data["vehicle_code"]).first()
            if existing_code:
                raise ValueError("Der Fahrzeug-Code existiert bereits.")

            existing_qr = Vehicle.query.filter_by(qr_code=data["qr_code"]).first()
            if existing_qr:
                raise ValueError("Der QR-Code existiert bereits.")

            vehicle = Vehicle(
                vehicle_code=data["vehicle_code"],
                qr_code=data["qr_code"],
                owner_id=current_user.id,
                vehicle_type_id=data["vehicle_type_id"],
                battery_level=data["battery_level"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                status=data["status"],
                is_active=(data["status"] != "inactive"),
            )
            db.session.add(vehicle)
            db.session.commit()
            flash("Fahrzeug wurde gespeichert.", "success")
            return redirect(url_for("main.dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("vehicle_form.html", vehicle=None, vehicle_types=vehicle_types)


@main_bp.route("/provider/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("provider")
def edit_vehicle(vehicle_id):
    vehicle = Vehicle.query.filter_by(id=vehicle_id, owner_id=current_user.id).first_or_404()
    vehicle_types = VehicleType.query.filter_by(is_active=True).all()

    if request.method == "POST":
        try:
            data = parse_vehicle_form(request.form)

            existing_code = Vehicle.query.filter_by(vehicle_code=data["vehicle_code"]).first()
            if existing_code and existing_code.id != vehicle.id:
                raise ValueError("Der Fahrzeug-Code existiert bereits.")

            existing_qr = Vehicle.query.filter_by(qr_code=data["qr_code"]).first()
            if existing_qr and existing_qr.id != vehicle.id:
                raise ValueError("Der QR-Code existiert bereits.")

            vehicle.vehicle_code = data["vehicle_code"]
            vehicle.qr_code = data["qr_code"]
            vehicle.vehicle_type_id = data["vehicle_type_id"]
            vehicle.battery_level = data["battery_level"]
            vehicle.latitude = data["latitude"]
            vehicle.longitude = data["longitude"]
            vehicle.status = data["status"]
            vehicle.is_active = data["status"] != "inactive"

            db.session.commit()
            flash("Fahrzeug wurde aktualisiert.", "success")
            return redirect(url_for("main.dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("vehicle_form.html", vehicle=vehicle, vehicle_types=vehicle_types)


@main_bp.route("/provider/vehicles/<int:vehicle_id>/deactivate", methods=["POST"])
@login_required
@role_required("provider")
def deactivate_vehicle(vehicle_id):
    vehicle = Vehicle.query.filter_by(id=vehicle_id, owner_id=current_user.id).first_or_404()
    if Rental.query.filter_by(vehicle_id=vehicle.id, status="active").first():
        flash("Fahrzeug kann nicht deaktiviert werden, weil es gerade ausgeliehen ist.", "danger")
        return redirect(url_for("main.dashboard"))

    vehicle.is_active = False
    vehicle.status = "inactive"
    db.session.commit()
    flash("Fahrzeug wurde deaktiviert.", "info")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/provider/vehicles/<int:vehicle_id>/activate", methods=["POST"])
@login_required
@role_required("provider")
def activate_vehicle(vehicle_id):
    vehicle = Vehicle.query.filter_by(id=vehicle_id, owner_id=current_user.id).first_or_404()

    vehicle.is_active = True
    if vehicle.status == "inactive":
        vehicle.status = "available"

    db.session.commit()
    flash("Fahrzeug wurde wieder aktiviert.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/driver/payment-methods/new", methods=["GET", "POST"])
@login_required
@role_required("driver")
def create_payment_method():
    if request.method == "POST":
        method = PaymentMethod(
            user_id=current_user.id,
            method_type=request.form.get("method_type", "card"),
            provider_name=request.form.get("provider_name", "").strip(),
            masked_details=request.form.get("masked_details", "").strip(),
            is_default=request.form.get("is_default") == "on",
        )

        if method.is_default:
            PaymentMethod.query.filter_by(user_id=current_user.id, is_default=True).update({"is_default": False})

        db.session.add(method)
        db.session.commit()
        flash("Zahlungsmittel gespeichert.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("payment_method_form.html")


@main_bp.route("/driver/rent/<int:vehicle_id>", methods=["POST"])
@login_required
@role_required("driver")
def rent_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    payment_method = PaymentMethod.query.filter_by(user_id=current_user.id, is_default=True).first()
    try:
        start_rental(current_user, vehicle, payment_method)
        flash("Ausleihe gestartet.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/driver/scan", methods=["GET", "POST"])
@login_required
@role_required("driver")
def scan_qr():
    if request.method == "POST":
        qr_code = request.form.get("qr_code", "").strip()
        vehicle = Vehicle.query.filter_by(qr_code=qr_code, is_active=True).first()
        if not vehicle:
            flash("QR-Code nicht gefunden.", "danger")
            return render_template("scan_qr.html")
        return redirect(url_for("main.vehicle_detail", vehicle_id=vehicle.id))
    return render_template("scan_qr.html")


@main_bp.route("/vehicles/<int:vehicle_id>")
@login_required
def vehicle_detail(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    return render_template("vehicle_detail.html", vehicle=vehicle)


@main_bp.route("/driver/return/<int:rental_id>", methods=["GET", "POST"])
@login_required
@role_required("driver")
def return_vehicle(rental_id):
    rental = Rental.query.filter_by(id=rental_id, user_id=current_user.id).first_or_404()
    if request.method == "POST":
        try:
            kilometers = Decimal(request.form.get("kilometers", "0").strip())
        except (InvalidOperation, ValueError):
            flash("Kilometer müssen eine gültige Zahl sein. Beispiel: 2.40", "danger")
            return render_template("return_rental.html", rental=rental)

        try:
            finish_rental(rental, kilometers)
            flash("Fahrt abgeschlossen und Zahlung verarbeitet.", "success")
            return redirect(url_for("main.dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("return_rental.html", rental=rental)