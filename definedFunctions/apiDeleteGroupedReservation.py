from flask import jsonify, request
from model import db, RoomReservation, VenueReservation, Receipt

def delete_reservations():
    data = request.get_json()  # Get the JSON data from the request body
    reservation_ids = data.get('reservation_ids', [])
    guest_id = data.get('guest_id')  # Extract guest_id from the request
    reservation_type = data.get('type')  # Reservation type (room or venue)

    print("Reservation IDs received:", reservation_ids)
    print("Guest ID received:", guest_id)
    print("Reservation type received:", reservation_type)

    # Check if necessary data is provided
    if not reservation_ids:
        print("No reservation IDs provided")
        return jsonify({"error": "No reservation IDs provided"}), 400
    if not guest_id:
        print("No guest ID provided")
        return jsonify({"error": "No guest ID provided"}), 400
    if not reservation_type:
        print("No reservation type provided")
        return jsonify({"error": "No reservation type provided"}), 400

    try:
        # Start a transaction
        with db.session.begin():
            # If the type is "room", delete RoomReservations
            if reservation_type == "room" or reservation_type == "both":
                room_reservations = RoomReservation.query.filter(
                    RoomReservation.room_reservation_id.in_(reservation_ids)
                ).all()
                print("Room reservations to delete:", room_reservations)

                for reservation in room_reservations:
                    db.session.delete(reservation)

            # If the type is "venue", delete VenueReservations
            elif reservation_type == "venue" or reservation_type == "both":
                venue_reservations = VenueReservation.query.filter(
                    VenueReservation.venue_reservation_id.in_(reservation_ids)
                ).all()
                print("Venue reservations to delete:", venue_reservations)

                for reservation in venue_reservations:
                    db.session.delete(reservation)

            # Handle invalid type
            else:
                print("Invalid reservation type provided")
                return jsonify({"error": "Invalid reservation type provided"}), 400

            # Delete receipts linked to the guest_id
            receipts = Receipt.query.filter_by(guest_id=guest_id).all()
            print(f"Receipts for guest ID {guest_id}:", receipts)

            for receipt in receipts:
                # Clear relationships before deletion
                receipt.discounts = []  # Clear discounts relationship
                receipt.additional_fees = []  # Clear additional fees relationship
                db.session.delete(receipt)

        # Commit the changes if all deletions were successful
        print("Deletion successful")
        return jsonify({"message": "Successfully deleted specified reservations and receipts"}), 201

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting reservations: {str(e)}")  # Log the full error
        return jsonify({"error": str(e)}), 500
