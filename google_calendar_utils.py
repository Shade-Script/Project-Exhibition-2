import datetime
import os.path
import pickle
import re # For splitting slots string
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these SCOPES, delete the file token.pickle or clear session credentials.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
CLIENT_SECRET_FILE = 'client_secret.json'
# Note: Using pickle for token storage is less ideal for web apps vs. database storage.
# For simplicity here, we keep it, but be aware of concurrency issues if scaling.
TOKEN_PICKLE_FILE = 'token.pickle' # Less relevant now we use session storage

# Define the mapping from day names to weekday numbers (Monday=0)
DAY_TO_WEEKDAY = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
}
# Define the RRULE day mapping for Google Calendar
DAY_TO_RRULE = {
    "Monday": "MO", "Tuesday": "TU", "Wednesday": "WE",
    "Thursday": "TH", "Friday": "FR", "Saturday": "SA", "Sunday": "SU"
}


def get_credentials_from_session(credentials_dict):
    """Rebuilds credentials object from dictionary stored in session."""
    creds = None
    if not credentials_dict:
        print("Error: No credentials dictionary provided.")
        return None

    try:
        creds = Credentials.from_authorized_user_info(credentials_dict, SCOPES)

        # Check if token needs refresh and attempt it
        if creds and not creds.valid and creds.refresh_token:
            print("Refreshing expired token...")
            try:
                creds.refresh(Request())
                # IMPORTANT: The calling code (app.py) needs to update the session
                # with the potentially refreshed credentials. This function returns
                # the refreshed creds object.
                print("Token refreshed successfully.")
            except Exception as e:
                print(f"Error refreshing token: {e}")
                # Let the calling code handle this (e.g., force re-auth)
                return None # Indicate refresh failure

        return creds

    except Exception as e:
        print(f"Error rebuilding credentials from dict: {e}")
        return None


def get_calendar_service(credentials_dict=None):
    """Builds the Google Calendar service object using credentials from session dict."""
    creds = get_credentials_from_session(credentials_dict)

    if not creds:
        print("Could not obtain valid credentials from session.")
        return None, None # Return None for service and creds

    # Check if credentials became invalid after potential refresh attempt
    if not creds.valid:
         print("Credentials are still invalid after checking/refreshing.")
         # This might happen if refresh token is revoked or expired
         return None, None

    try:
        service = build('calendar', 'v3', credentials=creds)
        print("Google Calendar service created successfully.")
        # Return both service and the (potentially refreshed) creds object
        return service, creds
    except HttpError as error:
        print(f'An API error occurred building service: {error}')
        return None, creds # Return creds even if service build fails? Or None, None? Let's return None,None
    except Exception as e:
        print(f'An unexpected error occurred building the service: {e}')
        return None, None


def find_next_weekday(target_weekday, start_date_obj):
    """
    Finds the date of the first occurrence of a target weekday (0=Monday)
    on or after the start_date_obj.
    """
    days_ahead = target_weekday - start_date_obj.weekday()
    if days_ahead < 0:  # Target day passed relative to start_date's weekday
        days_ahead += 7
    return start_date_obj + datetime.timedelta(days=days_ahead)


def create_calendar_events(service, schedule_data, time_slots_mapping, start_date_str, end_date_str, user_timezone='UTC'):
    """
    Creates Google Calendar events based on the schedule within a specified date range.

    Args:
        service: Authorized Google Calendar service instance.
        schedule_data (list): List of dicts (potentially edited) from the frontend.
        time_slots_mapping (dict): The mapping from slots to days/times.
        start_date_str (str): Start date in 'YYYY-MM-DD' format.
        end_date_str (str): End date in 'YYYY-MM-DD' format.
        user_timezone (str): The IANA timezone string (e.g., 'America/New_York').

    Returns:
        tuple: (success_count, failure_count, error_messages)
    """
    success_count = 0
    failure_count = 0
    error_messages = []
    total_slots_to_process = 0

    if not service:
        error_messages.append("Calendar service is not available.")
        # Estimate failure count based on input data
        try:
             total_slots_to_process = sum(len(course.get("slots", [])) if isinstance(course.get("slots"), list) else len(re.split(r'[,\s]+', course.get("slots",""))) for course in schedule_data)
        except:
            total_slots_to_process = len(schedule_data) # Rough estimate
        return 0, total_slots_to_process, error_messages

    if not schedule_data:
        print("No schedule data provided to create events.")
        return 0, 0, []

    # --- Parse Start and End Dates ---
    try:
        start_date_obj = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date_obj = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        # Format end date for RRULE UNTIL (inclusive, using YYYYMMDD format)
        # Google Calendar API expects YYYYMMDD or YYYYMMDDTHHMMSSZ. YYYYMMDD is simpler.
        # It represents the end of the day on that date in the calendar's timezone.
        until_date_str = end_date_obj.strftime('%Y%m%d')
    except ValueError:
        error_messages.append("Invalid start or end date format. Please use YYYY-MM-DD.")
        try:
             total_slots_to_process = sum(len(course.get("slots", [])) if isinstance(course.get("slots"), list) else len(re.split(r'[,\s]+', course.get("slots",""))) for course in schedule_data)
        except:
            total_slots_to_process = len(schedule_data)
        return 0, total_slots_to_process, error_messages

    # --- Process Each Course Entry ---
    processed_slot_identifiers = set() # Use (course_code, slot_code) to track uniqueness per course

    for course_index, course in enumerate(schedule_data):
        course_code = course.get("course_code", f"Course_{course_index+1}")
        course_name = course.get("course_name", "Unnamed Course")
        faculty = course.get("faculty_name", "")
        venue = course.get("venue", "")
        slots_raw = course.get("slots", []) # Get potentially edited slots

        # --- Process Slots (Handle string from Tabulator or list from initial OCR) ---
        slots = []
        if isinstance(slots_raw, str):
            slots = [s.strip().upper() for s in re.split(r'[,\s]+', slots_raw) if s.strip()]
        elif isinstance(slots_raw, list):
            slots = [str(s).strip().upper() for s in slots_raw if str(s).strip()]
        else:
            print(f"Warning: Invalid slots format for {course_code}: {slots_raw}. Skipping slots.")

        if not slots:
            # print(f"Info: No valid slots found for {course_code} - {course_name}.")
            continue # Skip course if no valid slots

        total_slots_to_process += len(slots) # Increment count of slots we will attempt

        for slot_code in slots:
             # Avoid creating duplicate events if the same slot appears multiple times for the *same* course
             slot_identifier = (course_code, slot_code)
             if slot_identifier in processed_slot_identifiers:
                 print(f"Info: Skipping duplicate slot '{slot_code}' for course '{course_code}'.")
                 total_slots_to_process -= 1 # Adjust count as we are skipping this one
                 continue
             processed_slot_identifiers.add(slot_identifier)

             found_slot_mapping = False
             for day, day_slots in time_slots_mapping.items():
                 if slot_code in day_slots:
                     found_slot_mapping = True
                     slot_info = day_slots[slot_code]
                     start_time_str = slot_info["start"]
                     end_time_str = slot_info["end"]
                     target_weekday = DAY_TO_WEEKDAY[day]
                     rrule_day = DAY_TO_RRULE[day]

                     try:
                         # Calculate the date for the *first* event occurring on or after start_date
                         first_event_date = find_next_weekday(target_weekday, start_date_obj)

                         # Check if the first event date is beyond the end date
                         if first_event_date > end_date_obj:
                             print(f"Info: First occurrence of slot {slot_code} ({day} {start_time_str}) on {first_event_date} is after the end date {end_date_obj}. Skipping.")
                             # This specific slot instance is skipped, does not count as failure.
                             # We already counted it in total_slots_to_process, so decrement failure potential
                             # failure_count remains unchanged, success_count remains unchanged
                             break # Stop searching days for this specific slot_code

                         # Format datetime strings using ISO format
                         start_datetime_str = f"{first_event_date.isoformat()}T{start_time_str}:00"
                         end_datetime_str = f"{first_event_date.isoformat()}T{end_time_str}:00"

                         # Create Event Body with Recurrence Rule ending on UNTIL date
                         event_summary = f"{course_code} - {course_name}"
                         event_description_parts = []
                         if faculty: event_description_parts.append(f"Faculty: {faculty}")
                         if venue: event_description_parts.append(f"Venue: {venue}") # Add venue to desc
                         event_description_parts.append(f"Slot: {slot_code}")
                         event_description = "\n".join(event_description_parts)

                         event = {
                             'summary': event_summary,
                             'location': venue, # Location field
                             'description': event_description,
                             'start': {'dateTime': start_datetime_str, 'timeZone': user_timezone},
                             'end': {'dateTime': end_datetime_str, 'timeZone': user_timezone},
                             'recurrence': [
                                 # UNTIL date is inclusive
                                 f'RRULE:FREQ=WEEKLY;UNTIL={until_date_str};BYDAY={rrule_day}'
                             ],
                             'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 15}]},
                         }

                         # Insert Event
                         created_event = service.events().insert(calendarId='primary', body=event).execute()
                         # print(f"Event created: {created_event.get('htmlLink')}")
                         success_count += 1
                         break # Stop searching days once slot is found and processed for this course

                     except HttpError as error:
                         print(f"An API error occurred creating event for slot {slot_code} ({course_code}): {error}")
                         error_detail = f"API Error {error.resp.status}"
                         try: # Try to get more specific error message from response
                             err_json = json.loads(error.content.decode())
                             error_detail += f": {err_json.get('error', {}).get('message', 'Unknown API error')}"
                         except: pass # Ignore if content isn't JSON
                         error_messages.append(f"Slot {slot_code} ({course_code}): {error_detail}")
                         # failure_count is implicitly tracked (total - success)
                         break # Stop searching days for this slot on error
                     except Exception as e:
                         print(f"An unexpected error occurred creating event for slot {slot_code} ({course_code}): {e}")
                         error_messages.append(f"Slot {slot_code} ({course_code}): Unexpected error - {e}")
                         # failure_count is implicitly tracked
                         break # Stop searching days for this slot on error

             if not found_slot_mapping:
                 print(f"Warning: Slot code '{slot_code}' for course '{course_code}' not found in time_slots mapping.")
                 error_messages.append(f"Slot '{slot_code}' (Course: {course_code}) not found in mapping.")
                 # This slot couldn't be processed, counts towards failure implicitly.


    # Calculate final failure count
    failure_count = total_slots_to_process - success_count
    # Ensure failure count isn't negative if total_slots_to_process was miscalculated
    failure_count = max(0, failure_count)

    return success_count, failure_count, error_messages