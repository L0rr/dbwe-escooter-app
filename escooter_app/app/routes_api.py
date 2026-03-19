from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request

from .extensions import db
from .models import ApiToken, PaymentMethod, Rental, User, Vehicle
from .services import finish_rental, start_rental


api_bp = Blueprint("api", __name__, url_prefix="/api")


def token_auth_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token_value = auth_header.replace("Bearer ", "").strip()
        token = ApiToken.query.filter_by(token=token_value).first()
        if not token or token.expires_at < datetime.utcnow():
            return jsonify({"error": "Unauthorized"}), 401
        request.api_user = token.user
        return func(*args, **kwargs)

    return wrapper


@api_bp.post("/auth/token")
def api_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = ApiToken.generate(user.id, datetime.utcnow() + timedelta(hours=12))
    db.session.commit()
    return jsonify(
        {
            "token": token.token,
            "token_type": "Bearer",
            "expires_at": token.expires_at.isoformat() + "Z",
            "role": user.role,
        }
    )


@api_bp.get("/vehicles")
@token_auth_required
def list_vehicles():
    vehicles = Vehicle.query.filter_by(is_active=True).order_by(Vehicle.id.asc()).all()
    return jsonify(
        [
            {
                "id": v.id,
                "vehicle_code": v.vehicle_code,
                "qr_code": v.qr_code,
                "type": v.vehicle_type.name,
                "battery_level": v.battery_level,
                "latitude": float(v.latitude),
                "longitude": float(v.longitude),
                "status": v.status,
                "provider": v.owner.username,
            }
            for v in vehicles
        ]
    )


@api_bp.get("/vehicles/available")
@token_auth_required
def list_available_vehicles():
    vehicles = Vehicle.query.filter_by(status="available", is_active=True).all()
    return jsonify(
        [
            {
                "id": v.id,
                "vehicle_code": v.vehicle_code,
                "qr_code": v.qr_code,
                "type": v.vehicle_type.name,
                "battery_level": v.battery_level,
                "latitude": float(v.latitude),
                "longitude": float(v.longitude),
                "status": v.status,
            }
            for v in vehicles
        ]
    )


@api_bp.post("/rentals")
@token_auth_required
def create_rental_api():
    user = request.api_user
    if user.role != "driver":
        return jsonify({"error": "Only drivers can rent vehicles"}), 403

    data = request.get_json() or {}
    vehicle_id = data.get("vehicle_id")
    payment_method_id = data.get("payment_method_id")
    vehicle = Vehicle.query.get(vehicle_id)
    payment_method = None

    if payment_method_id:
        payment_method = PaymentMethod.query.filter_by(id=payment_method_id, user_id=user.id).first()

    if not vehicle:
        return jsonify({"error": "Vehicle not found"}), 404

    try:
        rental = start_rental(user, vehicle, payment_method)
        return jsonify(
            {
                "rental_id": rental.id,
                "status": rental.status,
                "start_time": rental.start_time.isoformat() + "Z",
            }
        ), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.post("/rentals/<int:rental_id>/return")
@token_auth_required
def return_rental_api(rental_id):
    user = request.api_user
    rental = Rental.query.filter_by(id=rental_id, user_id=user.id).first()
    if not rental:
        return jsonify({"error": "Rental not found"}), 404

    data = request.get_json() or {}
    kilometers = Decimal(str(data.get("kilometers", 0)))

    try:
        finish_rental(rental, kilometers)
        return jsonify(
            {
                "rental_id": rental.id,
                "duration_minutes": rental.duration_minutes,
                "kilometers": float(rental.kilometers),
                "price_total": float(rental.price_total),
                "payment_status": rental.payment.status,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_bp.get("/payments")
@token_auth_required
def list_payments():
    user = request.api_user
    payments = (
        db.session.query(Rental)
        .filter(Rental.user_id == user.id, Rental.status == "completed")
        .order_by(Rental.id.desc())
        .all()
    )
    return jsonify(
        [
            {
                "payment_id": r.payment.id,
                "rental_id": r.id,
                "amount": float(r.payment.amount),
                "status": r.payment.status,
                "vehicle_code": r.vehicle.vehicle_code,
                "created_at": r.payment.created_at.isoformat() + "Z",
            }
            for r in payments
            if r.payment
        ]
    )
