# Smart Parking System – Use Cases


## Use Case 1: User Searches for a Spot and Makes a Reservation

**Scenario:**
- User sees a list of parking lots with a name and address.
- **Request:** User selects one or more parking lots, and a single start and end time window.

**Component Responsibilities:**
	- **Frontend:**
		- Sends selected lot(s) and time window to FastAPI.
		- Receives a list of `{parking lot, available spaces, price, event_id}` items from FastAPI. **The `event_id` must be included in each item and preserved by the frontend.**
		- When the user books a spot, sends a booking request to FastAPI with user ID, lot ID, spot ID, price, and the corresponding `event_id` (from the selected lot/price object). This ensures FastAPI remains stateless and correctness is preserved.

	- **FastAPI:**
		- Receives the search request from the frontend.
		- Calls the Pricing Service using `BatchGetPrice` (preferred) or `GetPrice` for each lot via gRPC, passing all relevant fields.
		- Calls the Inventory Service to get available spots for each lot and time window.
		- Consolidates the results into a list of `{parking lot, available spaces, price, event_id}` items and returns this to the frontend.
		- On booking, receives the booking request from the frontend (including `event_id`).
		- Sends a booking request to the Inventory Service with user ID, lot ID, spot ID, and time window.
		- If Inventory Service confirms the booking, sends a success response to the frontend.
		- After a successful booking, calls `RecordBookingOutcome` for each price event in the batch:
			- For the booked lot: `booked = true` (using the `event_id` from the frontend)
			- For all other price events in the batch: `booked = false`
		- If Inventory Service cannot book the spot, sends a failure response to the frontend.

	- **Pricing Service:**
		- Provides dynamic prices via:
			- `GetPrice(GetPriceRequest) -> GetPriceResponse`
			- `BatchGetPrice(BatchGetPriceRequest) -> BatchGetPriceResponse`
		- Each price response includes: `price_per_hour`, `event_id`, `context_key`, `base_price`, `multiplier`, `batch_id`.
		- Receives booking outcome notifications from FastAPI:
			- `RecordBookingOutcome(RecordBookingOutcomeRequest) -> RecordBookingOutcomeResponse`
			- For the booked lot/price: `booked = true`
			- For all other lot/price pairs: `booked = false`
		- Updates its RL bandit model accordingly.

	- **Inventory Service:**
		- Provides a list of available spots for each lot and time window.
		- Attempts to book the requested spot for the user and time window.
		- Returns success/failure to FastAPI.

**Result:**
- List of `{parking lot, available spaces, price, event_id}` items is shown to the user.
- User can then reserve one of the spots.
- User receives a confirmation: "Your reservation was successful." or a failure message if booking was not possible.

### Call Flow (Detailed)

1. **Frontend → FastAPI:**
   - Sends API call with selected lots and time window. 
2. **FastAPI → Inventory Service:**
   - Calls `GetLotOccupancy` for each lot to get availability.
3. **FastAPI:**
   - Stores occupancy results for each lot.
4. **FastAPI → Pricing Service:**
	- For each lot with at least one available spot, calls `GetPrice` to get prices.
5. **FastAPI:**
   - Consolidates `{parking lot, available spaces, price, event_id}` for each lot and sends this list to the frontend.
IMPLEMENTED UP TO HERE
6. **Frontend → FastAPI:**
   - User selects a lot and sends a booking request (or decline) to FastAPI, including the `event_id`, `lot_id`, `user_id`, `start_time`, `end_time`, `price`. 
7. **FastAPI → Inventory Service:**
   - If booking, calls ReserveSpot gRPC method to reserve the spot for the user and time window.
8. **Inventory Service → Pricing Service:**
	- Before booking, Inventory Service calls `RecordBookingOutcome` for the selected `event_id` (with user and price verification). This ensures the price, event, and user align and prevents client-side tampering.
9. **FastAPI → Frontend:**
   - Returns booking success/failure to the frontend.
---


## Use Case 2: User Views Their Reservations

**Scenario:**
- **Request:** User provides their User ID.

**Component Responsibilities:**
	- **Frontend:** Sends the User ID to FastAPI.
	- **FastAPI:**
		- Receives the User ID from the frontend.
		- Calls the Inventory Service to get a list of reservations for that User ID.
		- Returns the reservations as a list of `{reservation id, spot id, lot id, time, price}` items to the frontend.
	- **Inventory Service:** Provides a list of reservations for the given User ID.
- **Result:** System returns a list of `{reservation id, spot id, lot id, time, price}` items to the user.

### Call Flow (Detailed)

1. **Frontend → FastAPI:**
   - Sends API call with the user’s user_id.

2. **FastAPI → Inventory Service:**
   - Calls the `ListReservations` gRPC method with the user_id.

3. **Inventory Service:**
   - Returns a list of reservations for that user, each with fields like reservation_id, spot_id, lot_id, status, start_time, end_time, price_at_booking.

4. **FastAPI:**
   - Receives the reservation list and (optionally) parses/filters it.
   - Returns a list of `{reservation_id, spot_id, lot_id, status, start_time, end_time, price_at_booking}` items to the frontend.

5. **Frontend:**
   - Displays the list of reservations to the user.
---

## Use Case 3 (Optional): User Cancels a Reservation


- **Component Responsibilities:**
	- **Frontend:** Sends the User ID and Reservation ID to FastAPI.
	- **FastAPI:**
		- Receives the cancellation request.
		- Checks that the cancellation is at least one hour before the reservation start time.
		- If valid, sends the cancellation request to the Inventory Service.
		- Receives success/failure from Inventory Service and returns the appropriate message to the frontend.
		- If not valid (too late), returns a failure message to the frontend without contacting Inventory Service.


---

## Use Case 4: Frontend Needs the List of Parking Lots

**Scenario:**
- **Request:** Frontend requests the list of all parking lots and their addresses (no additional data required).

**Component Responsibilities:**
	- **Frontend:**
		- Sends an API call to FastAPI to request the list of parking lots.
	- **FastAPI:**
		- Receives the request from the frontend.
		- Makes a gRPC call to the Inventory Service to get the list of parking lots and their addresses. *(gRPC method needs to be implemented)*
		- Returns the list to the frontend.
	- **Inventory Service:**
		- Provides a list of all parking lots and their addresses.

**Result:**
- System returns a list of `{lot_id, lot_name, address}` items to the frontend for display.

### Call Flow (Detailed)

1. **Frontend → FastAPI:**
   - Sends API call to request the list of parking lots.
2. **FastAPI → Inventory Service:**
   - Calls `ListParkingLots` gRPC method (to be implemented).
3. **Inventory Service:**
   - Returns a list of parking lots and their addresses.
4. **FastAPI → Frontend:**
   - Returns the list to the frontend.

---

## Use Case 5: Create a New User

**Scenario:**
- **Request:** Frontend sends new user information (username, email) to FastAPI to create a new user account.

**Component Responsibilities:**
	- **Frontend:**
		- Sends user info (username, email) to FastAPI.
	- **FastAPI:**
		- Receives the user info from the frontend.
		- Forwards the info to the Inventory Service in a gRPC call to create the user. *(gRPC method needs to be implemented)*
		- Returns a boolean indicating success, and the user ID if successful, to the frontend.
	- **Inventory Service:**
		- Attempts to create a new user in the database.
		- Returns a boolean indicating success (false if username or email already exists), and the new user ID if successful.

**Result:**
- System returns a success/failure boolean and user ID (if successful) to the frontend for display or further use.

### Call Flow (Detailed)

1. **Frontend → FastAPI:**
   - Sends API call with new user info (username, email).
2. **FastAPI → Inventory Service:**
   - Calls `CreateUser` gRPC method (to be implemented) with the user info.
3. **Inventory Service:**
   - Attempts to create the user in the database.
   - Returns success/failure boolean and user ID (if successful).
4. **FastAPI → Frontend:**
   - Returns the result to the frontend.
- **Result:** System returns a success or failure message confirming the cancellation status.



