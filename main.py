import base64
import bcrypt
from flask import Flask, request, jsonify, Response, session
from marshmallow import Schema, fields, validate, ValidationError
from flask_marshmallow import Marshmallow  # Correct import
from werkzeug.utils import secure_filename  # For secure image uploads
from flask_cors import CORS
from model import db, Account, Room, RoomType, Venue, VenueReservation, RoomReservation, GuestDetails
from datetime import datetime, time
from defaultValues import rooms, roomTypes, venues
from sqlalchemy import or_

app = Flask(__name__)
CORS(app)

# Configuration for MySQL database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:''@localhost/lantaka_database'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy and Marshmallow
db.init_app(app)  # Initialize with app
ma = Marshmallow(app)  # Correct initialization

# Marshmallow schema for validation
class AccountSchema(Schema):
    account_role = fields.Str(required=True, validate=validate.OneOf(["Administrator", "Employee"]))
    fName = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    lName = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))
    phone = fields.Str(required=True, validate=validate.Length(min=10, max=15))
    dob = fields.Date(required=True)
    gender = fields.Str(validate=validate.OneOf(["male", "female"]))

# Initialize schema objects
account_schema = AccountSchema()
accounts_schema = AccountSchema(many=True)

# Route for account registration
@app.route('/register', methods=['POST'])
def register():
    try:
        # Validate the request form data
        data = account_schema.load(request.form)

        # Extract values after validation
        role = data['account_role']
        firstName = data['fName']
        lastName = data['lName']
        username = firstName.lower() + lastName.lower()
        email = data['email']
        password = data['password']
        phone = data['phone']
        dob = data['dob']
        gender = data['gender']

        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())


        # Check if the account already exists
        existing_accounts = Account.query.filter_by(account_email=email).first()
        if existing_accounts:
            return jsonify({"message": "Email already exists"}), 400

        # Create a new account
        new_account = Account(
            account_role=role,
            account_fName=firstName,
            account_lName=lastName,
            account_username=username,
            account_email=email,
            account_password=hashed_password.decode('utf-8'),
            account_phone=phone,
            account_dob=dob,
            account_gender=gender,
            account_status="active",
            account_last_login=""
        )

        # Add and commit to the database
        db.session.add(new_account)
        db.session.commit()

        return jsonify({"message": "success"}), 201

    except ValidationError as err:
        # Return validation errors from Marshmallow
        return jsonify({"errors": err.messages}), 400
    
@app.route('/api/submitReservation', methods=['POST'])
def submit_reservation():
    try:
        data = request.json  # Get JSON data from the request
        
        # Check if the account_id exists in the Account table
        account_id = data['accountId']
        account = db.session.query(Account).filter_by(account_id=account_id).first()
        if not account:
            return jsonify({'error': 'Invalid account ID'}), 400  # Return an error if account_id doesn't exist

        # Create GuestDetails entry
        new_guest = GuestDetails(
            guest_type=data['clientType'],
            guest_fName=data['firstName'],
            guest_lName=data['lastName'],
            guest_pop=None,  # Adjust if you plan to handle images/binary data
            guest_email=data['email'],
            guest_phone=data['phone'],
            guest_gender=data['gender'],
            guest_messenger_account=data['messengerAccount'],
            guest_poi=None,  # Adjust if you plan to handle images/binary data
            guest_designation=data['designation'],
            guest_address=data['address'],
            guest_client=data['clientAlias']
        )

        # Add the new guest to the session and flush to generate a guest_id
        db.session.add(new_guest)
        db.session.flush()  # Generates guest_id without committing

        # Parse date range and set check-in/check-out times
        date_start = datetime.fromisoformat(data['dateRange']['from'].replace('Z', ''))
        date_end = datetime.fromisoformat(data['dateRange']['to'].replace('Z', ''))
        check_in_time = time(13, 0)  # Fixed check-in time at 1 PM
        check_out_time = time(12, 0)  # Fixed check-out time at 12 PM (noon)

        # Create RoomReservation entries for each selected room
        for room_id in data['selectedReservation']:
            new_reservation = RoomReservation(
                room_id=room_id,
                guest_id=new_guest.guest_id,  # Use the guest_id from new_guest
                account_id=account_id,  # Use the provided account_id
                room_reservation_booking_date_start=date_start.date(),
                room_reservation_booking_date_end=date_end.date(),
                room_reservation_check_in_time=check_in_time,
                room_reservation_check_out_time=check_out_time,
                room_reservation_status="waiting"
            )

            # Add each room reservation to the session
            db.session.add(new_reservation)

        # Commit both guest and reservation(s) to the database
        db.session.commit()

        return jsonify({'message': 'Reservation submitted successfully!'}), 201

    except Exception as e:
        db.session.rollback()  # Rollback in case of error
        return jsonify({'error': str(e)}), 400# Return error message if something goes wrong


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']

    # Find the user by username
    user = Account.query.filter_by(account_username=username).first()

    if user and bcrypt.checkpw(password.encode('utf-8'), user.account_password.encode('utf-8')):
        # Update last login time
        user.account_last_login = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.commit()


        
        # Return relevant user data
        return jsonify({
            "message": "Login successful",
            "account_id": user.account_id,
            "role": user.account_role,
            "first_name": user.account_fName,
            "last_name": user.account_lName,
            "email": user.account_email,
            "phone": user.account_phone,
            "dob": user.account_dob.strftime('%Y-%m-%d'),  # Format date
            "gender": user.account_gender,
            "status": user.account_status,
            "last_login": user.account_last_login
        }), 200 
    else:
        return jsonify({"message": "Invalid credentials"}), 401


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    users = Account.query.all()
    if users:
        accounts = []
        for user in users:
            # Convert the blob (user.account_img) to a base64 string
            if user.account_img:
                image_blob = base64.b64encode(user.account_img).decode('utf-8')
                image_url = f"data:image/jpeg;base64,{image_blob}"  # Assuming it's a JPEG, adjust if needed
            else:
                image_url = None  # Or a default image

            account_data = {
                "id": user.account_id,
                "email": user.account_email,
                "firstName": user.account_fName,
                "lastName": user.account_lName,
                "username": user.account_username,
                "imageUrl": image_url,  # Send the base64 string to the frontend
                "role": user.account_role,  # Include role in profile data
                "PhoneNumber": user.account_phone,
                "dob": user.account_dob.strftime('%Y-%m-%d'),  # Format date
                "gender": user.account_gender,
                "status": user.account_status,
                "created_at": user.account_created_at.strftime('%Y-%m-%d'), # Format
                "updated_at": user.account_updated_at.strftime('%Y-%m-%d'),
            }
            accounts.append(account_data)

        return jsonify(accounts), 200
    else:
        return jsonify({"error": "No accounts found"}), 404



@app.route('/api/venueData', methods=['GET'])
def get_venue_data():
    venues = Venue.query.all()
    if venues:
        venuesHolder = []
        for venue in venues:
            if venue.venue_img:
                venue_image_blob = base64.b64encode(venue.venue_img).decode('utf-8')
                venue_image_url = f"data:image/webp;base64,{venue_image_blob}"  # Assuming it's a JPEG, adjust if needed
            else:
                venue_image_url = None  # Or a default image

            venue_data = {
                "id": venue.venue_id,
                "name": venue.venue_name,
                "description": venue.venue_description,
                "status": venue.venue_status,
                "price": venue.venue_pricing,
                "capacity": venue.venue_capacity,
                "image": venue_image_url,
            }
            venuesHolder.append(venue_data)

        return jsonify(venuesHolder), 200
    else:
        return jsonify({"error": "No venue data found"}), 404


@app.route('/api/roomData', methods=['GET'])
def get_room_data():
    rooms = Room.query.all()
    if rooms:
        roomsHolder = []
        for room in rooms:
            if room.room_type and room.room_type.room_type_img:
                room_image_blob = base64.b64encode(room.room_type.room_type_img).decode('utf-8')
                room_image_url = f"data:image/webp;base64,{room_image_blob}"  # Assuming it's a JPEG, adjust if needed
            else:
                room_image_url = None  # Or a default image

            room_data = {
                "id": room.room_id,
                "name": room.room_name,
                "type": room.room_type.room_type_name,
                "description": room.room_type.room_type_description,
                "status": room.room_status,
                "image": room_image_url,
            }
            roomsHolder.append(room_data)
        return jsonify(roomsHolder), 200
    else:
        return jsonify({"error": "No room data found"}), 404
    
@app.route('/api/details/rooms/<string:item_id>', methods=['GET'])
def get_room_details(item_id):
    currentDate = request.args.get('date')
    room = Room.query.get(item_id)
    if room:
        return get_room_details_response(room, currentDate)
    return jsonify({'error': 'Room not found'}), 404

@app.route('/api/details/venues/<string:item_id>', methods=['GET'])
def get_venue_details(item_id):
    currentDate = request.args.get('date')
    venue = Venue.query.get(item_id)
    if venue:
        return get_venue_details_response(venue, currentDate)
    return jsonify({'error': 'Venue not found'}), 404


def get_room_details_response(room , currentDate):
    current_booking = RoomReservation.query.filter_by(room_id=room.room_id).filter(
        (RoomReservation.room_reservation_booking_date_start <= currentDate) & 
        (RoomReservation.room_reservation_booking_date_end >= currentDate)).first()
    if current_booking:
        print(current_booking)
        return jsonify({
            'date': currentDate,
            'name': room.room_name,
            'type': 'room',
            'employee': f"{current_booking.account.account_fName} {current_booking.account.account_lName}",
            'guest_name': f"{current_booking.guest.guest_fName} {current_booking.guest.guest_lName}" if current_booking else None,
            'check_in': current_booking.room_reservation_booking_date_start.isoformat() if current_booking else None,
            'check_out': current_booking.room_reservation_booking_date_end.isoformat() if current_booking else None,
            'image_url': f"http://localhost:5000/api/image/{room.room_id}?type=room"
        })
    else:
         return jsonify({
            'date': currentDate,
            'name': room.room_name,
            'type': 'room',
            'guest_name': "No Reservation",
            'check_in': "No Reservation",
            'check_out': "No Reservation",
            'image_url': f"http://localhost:5000/api/image/{room.room_id}?type=room"
        })

def get_venue_details_response(venue, currentDate):
    current_booking = VenueReservation.query.filter_by(venue_id=venue.venue_id).filter(
        (VenueReservation.venue_reservation_booking_date_start <= currentDate) & 
        (VenueReservation.venue_reservation_booking_date_end >= currentDate)).first()
    if current_booking:
        return jsonify({
            'name': venue.venue_name,
            'type': 'venue',
            'employee': f"{current_booking.account.account_fName} {current_booking.account.account_lName}",
            'guest_name': f"{current_booking.guest.guest_fName} {current_booking.guest.guest_lName}" if current_booking else None,
            'check_in': current_booking.venue_reservation_booking_date_start.isoformat() if current_booking else None,
            'check_out': current_booking.venue_reservation_booking_date_end.isoformat() if current_booking else None,
            'image_url': f"http://localhost:5000/api/image/{venue.venue_id}?type=venue"
        })
    else:
         return jsonify({
            'date': currentDate,
            'name': venue.venue_name,
            'type': 'venue',
            'guest_name': "No Reservation",
            'check_in': "No Reservation",
            'check_out': "No Reservation",
            'image_url': f"http://localhost:5000/api/image/{venue.venue_id}?type=venue"
        })


@app.route('/api/image/<string:item_id>', methods=['GET'])
def serve_image(item_id):
    item_type = request.args.get('type')
    if item_type == 'room':
        room = Room.query.get(item_id)
        if room and room.room_type and room.room_type.room_type_img:
            return Response(room.room_type.room_type_img, mimetype='image/webp')
    elif item_type == 'venue':
        venue = Venue.query.get(item_id)
        if venue and venue.venue_img:
            return Response(venue.venue_img, mimetype='image/webp')
    return jsonify({'error': 'Image not found'}), 404


@app.route('/api/reservationCalendar', methods=['GET'])
def get_reservation_calendar():
    reservationsVenue = VenueReservation.query.all()
    reservationsRoom = RoomReservation.query.all()
    if reservationsVenue or reservationsRoom:
        reservations = []

        for venue in reservationsVenue:
            reservations.append({
                'reservationid': venue.venue_reservation_id,
                'id': venue.venue_id,
                'type':'venue',
                'dateStart': venue.venue_reservation_booking_date_start.isoformat(),
                'dateEnd': venue.venue_reservation_booking_date_end.isoformat(),
                'status': venue.venue_reservation_status,
                'guests': f"{venue.guest.guest_fName} {venue.guest.guest_lName}",
                'employee': f"{venue.account.account_fName} {venue.account.account_lName}",
                'checkIn': venue.venue_reservation_check_in_time.isoformat(),
                'checkOut': venue.venue_reservation_check_out_time.isoformat(),
            })

        for room in reservationsRoom:
            reservations.append({
                'reservationid': room.room_reservation_id,
                'id': room.room_id,
                'type':'room',
                'dateStart': room.room_reservation_booking_date_start.isoformat(),
                'dateEnd': room.room_reservation_booking_date_end.isoformat(),
                'status': room.room_reservation_status,
                'guests': f"{room.guest.guest_fName} {room.guest.guest_lName}",
                'employee': f"{room.account.account_fName} {room.account.account_lName}",
                'checkIn': room.room_reservation_check_in_time.isoformat(),
                'checkOut': room.room_reservation_check_out_time.isoformat(),
            })

        return jsonify(reservations), 200
    else:
        return jsonify({"error": "No reservations found"}), 404



# @app.route('/api/available/<string:dateStart>/<string:dateEnd>/<string:type>', methods=['GET'])
# def get_availability(dateStart, dateEnd, type):
#     # Convert string dates to date objects
#     date_start = datetime.strptime(dateStart, '%Y-%m-%d').date()
#     date_end = datetime.strptime(dateEnd, '%Y-%m-%d').date()

#     # Initialize a dictionary to hold available counts by type and room/venue type
#     availabilityRoom = {}
#     availabilityVenue = {}
#     availabilityBoth = {}

#     match type:
#         case "room":
#             room_types = RoomType.query.all()

#             for room_type in room_types:
#                 # Get the total number of rooms of this room type
#                 total_rooms = Room.query.filter_by(room_type_id=room_type.room_type_id).count()

#                 # Count reserved rooms that overlap with the provided dates
#                 reserved_rooms = RoomReservation.query.filter(
#                     db.and_(
#                         RoomReservation.room_reservation_booking_date_start < date_end,
#                         RoomReservation.room_reservation_booking_date_end > date_start,
#                         RoomReservation.room.has(room_type_id=room_type.room_type_id)
#                     )
#                 ).count()

#                 # Calculate available rooms
#                 available_rooms = total_rooms - reserved_rooms

#                 # Store the available room count in the dictionary
#                 availabilityRoom[f"room_{room_type.room_type_name}"] = available_rooms

#                 return jsonify(availabilityRoom), 200

#         case "venue":
#             venues = Venue.query.all()

#             for venue in venues:
#                 # Check if there are any reservations that overlap with the provided date range for the venue
#                 reserved_venues = VenueReservation.query.filter(
#                     db.and_(
#                         VenueReservation.venue_reservation_booking_date_start < date_end,
#                         VenueReservation.venue_reservation_booking_date_end > date_start,
#                         VenueReservation.venue_id == venue.venue_id
#                     )
#                 ).count()

#                 # If no reservations overlap with the date range, mark the venue as available (1), otherwise unavailable (0)
#                 available_venues = 1 if reserved_venues == 0 else 0

#                 # Store the available venue count in the dictionary
#                 availabilityVenue[f"venue_{venue.venue_name}"] = available_venues

#                 return jsonify(availabilityVenue), 200

#         case "both":
#             # Get all room types and venues
#             room_types = RoomType.query.all()

#             for room_type in room_types:
#                 # Get the total number of rooms of this room type
#                 total_rooms = Room.query.filter_by(room_type_id=room_type.room_type_id).count()

#                 # Count reserved rooms that overlap with the provided dates
#                 reserved_rooms = RoomReservation.query.filter(
#                     db.and_(
#                         RoomReservation.room_reservation_booking_date_start < date_end,
#                         RoomReservation.room_reservation_booking_date_end > date_start,
#                         RoomReservation.room.has(room_type_id=room_type.room_type_id)
#                     )
#                 ).count()

#                 # Calculate available rooms
#                 available_rooms = total_rooms - reserved_rooms

#                 # Store the available room count in the dictionary
#                 availabilityBoth[f"room_{room_type.room_type_name}"] = available_rooms
            
#             venues = Venue.query.all()

#             for venue in venues:
#                 # Check if there are any reservations that overlap with the provided date range for the venue
#                 reserved_venues = VenueReservation.query.filter(
#                     db.and_(
#                         VenueReservation.venue_reservation_booking_date_start < date_end,
#                         VenueReservation.venue_reservation_booking_date_end > date_start,
#                         VenueReservation.venue_id == venue.venue_id
#                     )
#                 ).count()

#                 # If no reservations overlap with the date range, mark the venue as available (1), otherwise unavailable (0)
#                 available_venues = 1 if reserved_venues == 0 else 0

#                 # Store the available venue count in the dictionary
#                 availabilityBoth[f"venue_{venue.venue_name}"] = available_venues

#             return jsonify(availabilityBoth), 200

#     # Return the combined availability information for rooms and venues


@app.route('/api/everythingAvailable', methods=['GET'])
def api_everythingAvailable():
    rooms = Room.query.all()
    
    # Group rooms by room type
    double_rooms = [room.to_dict(is_available=False) for room in rooms if room.room_type_id == 1]
    triple_rooms = [room.to_dict(is_available=False) for room in rooms if room.room_type_id == 2]
    matrimonial_rooms = [room.to_dict(is_available=False) for room in rooms if room.room_type_id == 3]

    return jsonify({
        "double_rooms": double_rooms,
        "triple_rooms": triple_rooms,
        "matrimonial_rooms": matrimonial_rooms
    })


@app.route('/api/availableRooms/<string:dateStart>/<string:dateEnd>', methods=['GET'])
def api_availableRooms(dateStart, dateEnd):
    # Convert string dates to date objects
    date_start = datetime.strptime(dateStart, '%Y-%m-%d').date()
    date_end = datetime.strptime(dateEnd, '%Y-%m-%d').date()

    # Get all rooms
    rooms = Room.query.all()
    
    available_rooms = []
    for room in rooms:
        # Query to find reservations that overlap with the requested date range
        overlapping_reservations = RoomReservation.query.filter(
            RoomReservation.room_id == room.room_id,
            RoomReservation.room_reservation_status == "waiting",
            RoomReservation.room_reservation_booking_date_start <= date_end,  # Starts on or before the requested end date
            RoomReservation.room_reservation_booking_date_end >= date_start   # Ends on or after the requested start date
        ).all()


        # Set room_status based on whether there are overlapping reservations
        room_status = len(overlapping_reservations) == 0  # True if no overlapping reservations
        room_dict = room.to_dict()
        room_dict['room_status'] = room_status  # Add the room status to each room dictionary
        available_rooms.append(room_dict)

    # Group available rooms by room type
    double_rooms = [room for room in available_rooms if room['room_type_id'] == 1]
    triple_rooms = [room for room in available_rooms if room['room_type_id'] == 2]
    matrimonial_rooms = [room for room in available_rooms if room['room_type_id'] == 3]

    return jsonify({
        "double_rooms": double_rooms,
        "triple_rooms": triple_rooms,
        "matrimonial_rooms": matrimonial_rooms
    })









@app.route('/api/available/<string:dateStart>/<string:dateEnd>/<string:type>', methods=['GET'])
def get_availability(dateStart, dateEnd, type):
    # Convert string dates to date objects
    date_start = datetime.strptime(dateStart, '%Y-%m-%d').date()
    date_end = datetime.strptime(dateEnd, '%Y-%m-%d').date()

    # Initialize dictionaries to hold available room IDs and venue availability
    available_rooms_by_type = {}
    available_venues = {}

    # Get all room types
    room_types = RoomType.query.with_entities(RoomType.room_type_id).all()
    venue_types = Venue.query.with_entities(Venue.venue_id, Venue.venue_name).all()  # Fetch venue_id and venue_name

    # Check available rooms by room type
    for room_type in room_types:
        total_rooms = Room.query.filter_by(room_type_id=room_type.room_type_id).all()

        reserved_room_ids = RoomReservation.query.filter(
            RoomReservation.room_reservation_booking_date_start < date_end,
            RoomReservation.room_reservation_booking_date_end > date_start,
            RoomReservation.room.has(room_type_id=room_type.room_type_id)
        ).with_entities(RoomReservation.room_id).all()

        reserved_ids = {room[0] for room in reserved_room_ids}
        available_rooms = [room.room_id for room in total_rooms if room.room_id not in reserved_ids]

        available_rooms_by_type[room_type.room_type_id] = available_rooms 

    # Check venue availability
    for venue_id, venue_name in venue_types:
        total_venues = Venue.query.filter_by(venue_id=venue_id).all()

        reserved_venue_ids = VenueReservation.query.filter(
            VenueReservation.venue_reservation_booking_date_start < date_end,
            VenueReservation.venue_reservation_booking_date_end > date_start,
            VenueReservation.venue.has(venue_id=venue_id)
        ).with_entities(VenueReservation.venue_id).all()

        reserved_venue_ids_set = {venue[0] for venue in reserved_venue_ids}
        is_available = venue_id not in reserved_venue_ids_set

        if is_available:
            available_venues[venue_id] = {
                "venue_name": venue_name,
                "available": True,
                "dates": [(date_start, date_end)]  # This indicates that it's available during this period
            }
        else:
            available_venues[venue_id] = {
                "venue_name": venue_name,
                "available": False,
                "dates": []  # No available dates if reserved
            }

    # Return results based on the requested type
    if type == 'both':
        return jsonify(availability={
            'rooms': available_rooms_by_type,
            'venues': available_venues
        }), 200
    elif type == 'room':
        return jsonify(availability=available_rooms_by_type), 200
    elif type == 'venue':
        return jsonify(availability=available_venues), 200

    return jsonify(error='Invalid type specified'), 400






    
@app.route('/api/reservationCalendar/<int:event_id>', methods=['PUT'])
def update_reservation_status(event_id):
    # Retrieve query parameters
    reservation_id = request.args.get('id')
    new_status = request.args.get('status')
    event_type = request.args.get('type')

    # Print values for debugging
    print(f"Reservation ID: {reservation_id}, Status: {new_status}, Event Type: {event_type}")

    # Check required fields
    if not reservation_id or not new_status or not event_type:
        return jsonify({'error': 'Missing required fields: id, status, or type'}), 400

    # Normalize case for event_type
    event_type = event_type.lower()

    try:
        # Update based on type
        if event_type == 'venue':
            reservation = VenueReservation.query.filter_by(venue_reservation_id=event_id).first()
            if reservation:
                reservation.venue_reservation_status = new_status
                db.session.commit()
                return jsonify({'message': 'Venue reservation status updated successfully'}), 200
            else:
                return jsonify({'error': 'Venue reservation not found'}), 404

        elif event_type == 'room':
            reservation = RoomReservation.query.filter_by(room_reservation_id=event_id).first()
            if reservation:
                reservation.room_reservation_status = new_status
                db.session.commit()
                return jsonify({'message': 'Room reservation status updated successfully'}), 200
            else:
                return jsonify({'error': 'Room reservation not found'}), 404

        else:
            return jsonify({'error': 'Invalid reservation type'}), 400

    except Exception as e:
        db.session.rollback()
        print(f"Error updating reservation: {e}")
        return jsonify({'error': 'An error occurred while updating the reservation'}), 500



@app.route('/api/reservationStatus/<string:date>', methods=['GET'])
def get_reservation_status(date):
    try:
        # Convert string date to datetime object
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()

        # Query venue reservations
        venue_reservations = VenueReservation.query.filter(
            VenueReservation.venue_reservation_booking_date_start <= date_obj,
            VenueReservation.venue_reservation_booking_date_end >= date_obj
        ).all()

        # Query room reservations
        room_reservations = RoomReservation.query.filter(
            RoomReservation.room_reservation_booking_date_start <= date_obj,
            RoomReservation.room_reservation_booking_date_end >= date_obj
        ).all()

        # Combine and format results
        reservation_data = []
        for reserve in venue_reservations:
            reservation_data.append({
                'id': reserve.venue_id,
                'status': reserve.venue_reservation_status,
                'type': 'venue'
            })
        for reserve in room_reservations:
            reservation_data.append({
                'id': reserve.room_id,
                'status': reserve.room_reservation_status,
                'type': 'room'
            })

        # If no reservations are found, set all statuses to normal
        if not reservation_data:
            # Create a list of all venues and rooms from your defined lists
            all_venues_and_rooms = [
                {'id': venue.venue_id, 'type': 'venue'} for venue in venues
            ] + [
                {'id': room.room_id, 'type': 'room'} for room in rooms
            ]

            for item in all_venues_and_rooms:
                reservation_data.append({
                    'id': item['id'],
                    'status': 'normal',
                    'type': item['type']
                })
            return jsonify(reservation_data), 200

        return jsonify(reservation_data), 200

    except ValueError:
        return jsonify({"error": "Invalid date format. Please use YYYY-MM-DD."}), 400



# Ensure the application context is active before creating tables
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Creates the tables in the database
        # Check if room types already exist
        existing_room_types = db.session.query(RoomType).all()
        if not existing_room_types:
            db.session.add_all(roomTypes)
            db.session.commit()
            print("Room types inserted successfully!")
        else:
            print("Room types already exist, skipping insertion.")

        # Check if rooms already exist
        existing_rooms = db.session.query(Room).all()
        if not existing_rooms:
            db.session.add_all(rooms)
            db.session.commit()
            print("Rooms inserted successfully!")
        else:
            print("Rooms already exist, skipping insertion.")

        # Check if venues already exist
        existing_venue = db.session.query(Venue).all()
        if not existing_venue:
            db.session.add_all(venues)
            db.session.commit()
            print("Venues inserted successfully!")
        else:
            print("Venues already exist, skipping insertion.")

        existing_dummy = db.session.query(VenueReservation).all()
        if not existing_dummy:
            # db.session.add_all(new_room_reservations)
            db.session.commit()
            print("dummies inserted successfully!")
        else:
            print("Venues already exist, skipping insertion.")


    app.run(host='0.0.0.0', debug=True, port=5000)
