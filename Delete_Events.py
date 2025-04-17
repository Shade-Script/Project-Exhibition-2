import os
import pickle
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# --- Configuration ---
# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar'] # Read/write access
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
CALENDAR_ID = 'primary'  # Use 'primary' for the main calendar,
                         # or the specific calendar ID for others.
CONFIRMATION_WORD = "DELETE" # Word user must type to confirm deletion

# --- Authentication ---
def get_calendar_service():
    """Shows basic usage of the Google Calendar API.
    Connects to the API, handling OAuth 2.0 flow.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                print("Deleting token file and re-authenticating...")
                os.remove(TOKEN_FILE)
                # Rerun the flow after removing the bad token
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                 print(f"ERROR: Credentials file '{CREDENTIALS_FILE}' not found.")
                 print("Please download it from Google Cloud Console and place it here.")
                 sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    try:
        service = build('calendar', 'v3', credentials=creds)
        print("Successfully connected to Google Calendar API.")
        return service
    except HttpError as error:
        print(f'An API error occurred: {error}')
        print("Details:", error.content)
        return None
    except Exception as e:
        print(f"An unexpected error occurred during service build: {e}")
        return None

# --- Main Logic ---
def main():
    """Deletes all events from the specified Google Calendar."""
    print("--- Google Calendar Event Deletion Script ---")
    print(f"Target Calendar ID: {CALENDAR_ID}")
    print("\n🚨🚨🚨 WARNING! 🚨🚨🚨")
    print("This script will attempt to delete ALL events from the specified calendar.")
    print("This action is PERMANENT and CANNOT BE UNDONE.")
    print("Consider backing up your calendar first (export .ics file).\n")

    confirm = input(f"To proceed, type the word '{CONFIRMATION_WORD}' exactly: ")

    if confirm != CONFIRMATION_WORD:
        print("Confirmation failed. Aborting script.")
        sys.exit(0)

    print("\nConfirmation received. Proceeding with deletion...")

    service = get_calendar_service()
    if not service:
        print("Failed to get Calendar service. Exiting.")
        sys.exit(1)

    page_token = None
    deleted_count = 0
    failed_count = 0

    print("Fetching events to delete...")
    while True:
        try:
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                pageToken=page_token,
                maxResults=250,  # Fetch in batches
                singleEvents=False # Important: Get master recurring events, not instances
            ).execute()
            events = events_result.get('items', [])

            if not events:
                print("No more events found.")
                break

            print(f"Found {len(events)} events in this batch...")

            for event in events:
                event_id = event['id']
                summary = event.get('summary', '(No Title)')
                try:
                    print(f"  Deleting event: {summary} (ID: {event_id})... ", end="")
                    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
                    print("Deleted.")
                    deleted_count += 1
                except HttpError as error:
                    # Handle cases where event might already be deleted or access issue
                    if error.resp.status == 404:
                         print(f"Skipped (Already deleted or not found - HTTP 404).")
                    elif error.resp.status == 410:
                         print(f"Skipped (Already deleted - HTTP 410 Gone).")
                    else:
                        print(f"FAILED! Error: {error}")
                        failed_count += 1
                except Exception as e:
                     print(f"FAILED! Unexpected Error: {e}")
                     failed_count += 1


            page_token = events_result.get('nextPageToken')
            if not page_token:
                print("All pages processed.")
                break # Exit the loop if no more pages

        except HttpError as error:
            print(f'\nAn API error occurred while listing events: {error}')
            print("Details:", error.content)
            print("Aborting further processing.")
            break
        except Exception as e:
            print(f'\nAn unexpected error occurred: {e}')
            print("Aborting further processing.")
            break


    print("\n--- Deletion Summary ---")
    print(f"Successfully deleted: {deleted_count} events.")
    if failed_count > 0:
        print(f"Failed to delete: {failed_count} events (check logs above for errors).")
    print(f"Target Calendar: {CALENDAR_ID}")
    print("------------------------")

if __name__ == '__main__':
    main()