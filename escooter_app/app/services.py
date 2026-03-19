from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import math
import secrets

from flask import current_app

from .extensions import db
from .models import Payment, Rental, Vehicle, money


def calculate_rental_price(vehicle_type, duration_minutes: int) -> Decimal:
    base_price = Decimal(vehicle_type.base_price)
    price_per_minute = Decimal(vehicle_type.price_per_minute)
    total = base_price + (price_per_minute * Decimal(duration_minutes))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def start_rental(user, vehicle: Vehicle, payment_method=None) -> Rental:
    active_rental = Rental.query.filter_by(user_id=user.id, status="active").first()
    if active_rental:
        raise ValueError("Du hast bereits eine laufende Ausleihe.")

    if vehicle.status != "available" or not vehicle.is_active:
        raise ValueError("Dieses Fahrzeug ist nicht verfügbar.")

    rental = Rental(user_id=user.id, vehicle_id=vehicle.id, payment_method_id=getattr(payment_method, "id", None))
    vehicle.status = "rented"
    db.session.add(rental)
    db.session.commit()
    return rental


def finish_rental(rental: Rental, kilometers: Decimal) -> Rental:
    if rental.status != "active":
        raise ValueError("Diese Ausleihe ist bereits abgeschlossen.")

    if Decimal(kilometers) < 0:
        raise ValueError("Kilometer dürfen nicht negativ sein.")

    rental.end_time = datetime.utcnow()
    seconds = max(60, int((rental.end_time - rental.start_time).total_seconds()))

    # Jede angefangene Minute zählt.
    rental.duration_minutes = max(1, math.ceil(seconds / 60))

    # Kilometer werden gespeichert, aber gemäss Aufgabenstellung nicht verrechnet.
    rental.kilometers = Decimal(kilometers).quantize(Decimal("0.01"))
    rental.price_total = calculate_rental_price(rental.vehicle.vehicle_type, rental.duration_minutes)
    rental.status = "completed"
    rental.vehicle.status = "available"

    payment = Payment(
        rental=rental,
        amount=money(rental.price_total),
        status="processed",
        transaction_reference=f"PAY-{secrets.token_hex(6).upper()}",
    )
    db.session.add(payment)
    db.session.commit()
    return rental