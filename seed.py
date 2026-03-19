from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import PaymentMethod, User, Vehicle, VehicleType
from app.services import finish_rental, start_rental


app = create_app()


with app.app_context():
    db.drop_all()
    db.create_all()

    scooter_type = VehicleType(
        code="escooter",
        name="E-Scooter",
        base_price=2.50,
        price_per_minute=0.35,
    )
    ebike_type = VehicleType(
        code="ebike",
        name="E-Bike",
        base_price=3.00,
        price_per_minute=0.30,
    )
    db.session.add_all([scooter_type, ebike_type])
    db.session.commit()

    provider1 = User(
        username="provider1",
        email="beispiel1@beispiel.ch",
        full_name="Beispiel Provider1",
        role="provider",
    )
    provider1.set_password("beispielpasswort")

    provider2 = User(
        username="provider2",
        email="beispiel2@beispiel.ch",
        full_name="Beispiel Provider2",
        role="provider",
    )
    provider2.set_password("beispielpasswort")

    driver1 = User(
        username="driver1",
        email="beispiel3@beispiel.ch",
        full_name="Beispiel Fahrer1",
        role="driver",
    )
    driver1.set_password("beispielpasswort")

    driver2 = User(
        username="driver2",
        email="beispiel4@beispiel.ch",
        full_name="Beispiel Fahrer2",
        role="driver",
    )
    driver2.set_password("beispielpasswort")

    db.session.add_all([provider1, provider2, driver1, driver2])
    db.session.commit()

    pm1 = PaymentMethod(
        user_id=driver1.id,
        method_type="card",
        provider_name="Visa",
        masked_details="**** 1111",
        is_default=True,
    )
    pm2 = PaymentMethod(
        user_id=driver2.id,
        method_type="twint",
        provider_name="TWINT",
        masked_details="0791234567",
        is_default=True,
    )
    db.session.add_all([pm1, pm2])
    db.session.commit()

    vehicles = [
        Vehicle(
            vehicle_code="SC-1001",
            qr_code="QR-SC-1001",
            owner_id=provider1.id,
            vehicle_type_id=scooter_type.id,
            battery_level=88,
            latitude=Decimal("46.948090"),
            longitude=Decimal("7.447440"),
            status="available",
            is_active=True,
        ),
        Vehicle(
            vehicle_code="SC-1002",
            qr_code="QR-SC-1002",
            owner_id=provider1.id,
            vehicle_type_id=scooter_type.id,
            battery_level=67,
            latitude=Decimal("46.947500"),
            longitude=Decimal("7.440100"),
            status="available",
            is_active=True,
        ),
        Vehicle(
            vehicle_code="SC-2001",
            qr_code="QR-SC-2001",
            owner_id=provider2.id,
            vehicle_type_id=scooter_type.id,
            battery_level=53,
            latitude=Decimal("46.950700"),
            longitude=Decimal("7.438600"),
            status="available",
            is_active=True,
        ),
        Vehicle(
            vehicle_code="EB-3001",
            qr_code="QR-EB-3001",
            owner_id=provider2.id,
            vehicle_type_id=ebike_type.id,
            battery_level=92,
            latitude=Decimal("46.946000"),
            longitude=Decimal("7.452000"),
            status="maintenance",
            is_active=True,
        ),
    ]
    db.session.add_all(vehicles)
    db.session.commit()

    # Eine fertige Demo-Fahrt, damit Zahlungen schon sichtbar sind.
    rental = start_rental(driver1, vehicles[0], pm1)
    rental.start_time = datetime.utcnow() - timedelta(minutes=18)
    db.session.commit()
    finish_rental(rental, Decimal("4.20"))

    print("Demo-Daten wurden erstellt.")
    print("Provider 1 Login: beispiel1@beispiel.ch / beispielpasswort (Username: provider1)")
    print("Provider 2 Login: beispiel2@beispiel.ch / beispielpasswort (Username: provider2)")
    print("Driver 1 Login: beispiel3@beispiel.ch / beispielpasswort (Username: driver1)")
    print("Driver 2 Login: beispiel4@beispiel.ch / beispielpasswort (Username: driver2)")