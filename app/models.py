from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import secrets

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # provider oder driver
    full_name = db.Column(db.String(120), nullable=False)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)

    vehicles = db.relationship("Vehicle", back_populates="owner", lazy=True)
    payment_methods = db.relationship("PaymentMethod", back_populates="user", lazy=True)
    rentals = db.relationship("Rental", back_populates="user", lazy=True)
    api_tokens = db.relationship("ApiToken", back_populates="user", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


class VehicleType(TimestampMixin, db.Model):
    __tablename__ = "vehicle_types"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    price_per_minute = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    vehicles = db.relationship("Vehicle", back_populates="vehicle_type", lazy=True)


class Vehicle(TimestampMixin, db.Model):
    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_code = db.Column(db.String(50), unique=True, nullable=False)
    qr_code = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey("vehicle_types.id"), nullable=False)
    battery_level = db.Column(db.Integer, nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=False)
    longitude = db.Column(db.Numeric(9, 6), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="available")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    owner = db.relationship("User", back_populates="vehicles")
    vehicle_type = db.relationship("VehicleType", back_populates="vehicles")
    rentals = db.relationship("Rental", back_populates="vehicle", lazy=True)


class PaymentMethod(TimestampMixin, db.Model):
    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    method_type = db.Column(db.String(30), nullable=False)
    provider_name = db.Column(db.String(50), nullable=False)
    masked_details = db.Column(db.String(50), nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="payment_methods")
    rentals = db.relationship("Rental", back_populates="payment_method", lazy=True)


class Rental(TimestampMixin, db.Model):
    __tablename__ = "rentals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id"), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    kilometers = db.Column(db.Numeric(8, 2), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    price_total = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")

    user = db.relationship("User", back_populates="rentals")
    vehicle = db.relationship("Vehicle", back_populates="rentals")
    payment_method = db.relationship("PaymentMethod", back_populates="rentals")
    payment = db.relationship("Payment", back_populates="rental", uselist=False)


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    rental_id = db.Column(db.Integer, db.ForeignKey("rentals.id"), unique=True, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="processed")
    transaction_reference = db.Column(db.String(80), unique=True, nullable=False)

    rental = db.relationship("Rental", back_populates="payment")


class ApiToken(TimestampMixin, db.Model):
    __tablename__ = "api_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(32))
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", back_populates="api_tokens")

    @staticmethod
    def generate(user_id: int, expires_at: datetime):
        token = ApiToken(user_id=user_id, expires_at=expires_at)
        db.session.add(token)
        return token


# Kleine Hilfsfunktion, damit Decimal sauber gerundet bleibt.
def money(value: float | Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))
