import os
import json # For parsing form data
import re   # Potentially needed if handling complex strings, though utils does it now
from flask import (
    Flask, request, redirect, url_for, render_template,
    flash, session, abort, jsonify # Added jsonify for potential API responses
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# --- Google Auth Imports ---
import google.oauth2.credentials
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# --- Local Imports ---
# Make sure these files are in the same directory or Python path
from ocr_script import run_ocr_and_extract, time_slots as default_time_slots
from google_calendar_utils import (
    get_calendar_service, create_calendar_events,
    CLIENT_SECRET_FILE, SCOPES # Import helper if needed here
)

# --- Flask App Setup ---
load_dotenv() # Load environment variables from .env file first

app = Flask(__name__)
# Use FLASK_SECRET_KEY from .env, fallback to a default (NOT recommended for production)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_replace_me")

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Increased max size slightly for larger images if needed
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024 # 20 MB max upload size

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Helper Functions ---
def allowed_file(filename):
    """Checks if the filename has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# credentials_to_dict is now primarily used within google_calendar_utils if needed,
# but keep it here if used directly in app routes (like OAuth callback)
def credentials_to_dict(credentials):
    """Helper to convert Google Credentials object to JSON serializable dict for session."""
    if not credentials: return None
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}


# --- Routes ---

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handles file upload, runs OCR, and redirects to results page."""
    if 'timetable_image' not in request.files:
        flash('No file part selected in the form.', 'warning')
        return redirect(url_for('index'))

    file = request.files['timetable_image']

    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        # Secure the filename before using it (though we read bytes directly now)
        filename = secure_filename(file.filename)
        print(f"Processing uploaded file: {filename}")

        try:
            # Read image data directly into memory
            image_data = file.read()
            # Simple mime type deduction from extension
            ext = filename.rsplit('.', 1)[1].lower()
            mime_type = f'image/{ext}' if ext != 'jpg' else 'image/jpeg'

            # --- Run OCR ---
            print("Starting OCR process...")
            extracted_data = run_ocr_and_extract(image_data, mime_type=mime_type)
            # run_ocr_and_extract now returns list or None on critical failure

            print(f"OCR process finished.") # Don't log potentially large data here by default

            if extracted_data is None:
                 # OCR failed critically (API key issue, safety block, network error after retries)
                 flash('OCR process failed critically. Check API key, network, or server logs.', 'danger')
                 # Clear any potential stale data from previous attempts
                 session.pop('extracted_data', None)
                 return redirect(url_for('index'))
            else:
                 # OCR completed, result is a list (potentially empty)
                 session['extracted_data'] = extracted_data # Store list (even if empty)
                 if not extracted_data:
                      print("OCR returned empty list.")
                      flash('OCR completed, but no schedule data could be extracted automatically. You can add rows manually below.', 'warning')
                 else:
                      print(f"OCR extracted {len(extracted_data)} item(s).")
                      flash('OCR successful! Review and edit the extracted data below.', 'success')
                 return redirect(url_for('show_results'))

        except Exception as e:
            # Catch broader exceptions during file read or unexpected OCR issues
            print(f"Error during file processing or OCR call: {e}", exc_info=True) # Log traceback
            flash(f'An error occurred processing the file: {e}', 'danger')
            return redirect(url_for('index'))

    else:
        flash('Invalid file type. Allowed types are png, jpg, jpeg, gif, webp.', 'warning')
        return redirect(url_for('index'))

@app.route('/results')
def show_results():
    """Displays the OCR results (editable table) stored in the session."""
    # Get data from session (could be list, empty list, or None if never set)
    extracted_data = session.get('extracted_data', None)
    google_authenticated = 'credentials' in session # Check if Google credentials are in session

    # If user lands here without ever uploading, extracted_data will be None
    if extracted_data is None:
         flash('No data found. Please upload an image first.', 'info')
         return redirect(url_for('index'))

    # Pass the data (list, possibly empty) to the template for Tabulator
    return render_template('results.html',
                           extracted_data=extracted_data,
                           google_authenticated=google_authenticated)

# --- Google OAuth Routes ---

@app.route('/authorize')
def authorize():
    """Initiates the Google OAuth flow."""
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"CRITICAL ERROR: {CLIENT_SECRET_FILE} not found.")
        return render_template('error.html', error_message=f"Server configuration error: {CLIENT_SECRET_FILE} not found. Cannot start authentication.")

    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    try:
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE, scopes=SCOPES)
    except Exception as e:
        print(f"Error loading client secrets file '{CLIENT_SECRET_FILE}': {e}")
        return render_template('error.html', error_message=f"Server configuration error reading client secrets: {e}")


    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client configured in the Google Cloud Console.
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline', # Request refresh token
        prompt='consent',      # Force consent screen for refresh token ensurence
        include_granted_scopes='true')

    # Store the state generated for CSRF protection.
    session['state'] = state
    # Store the intended destination page before redirecting to Google
    session['oauth_intended_url'] = url_for('show_results')

    print(f"Redirecting user to Google for authorization. State: {state}")
    # Redirect the user to Google's authorization server.
    return redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
    """Handles the callback from Google after user authorization."""
    print("Received callback from Google.")
    # Verify the state parameter to prevent CSRF attacks.
    state = session.get('state')
    request_state = request.args.get('state')
    print(f"Session state: {state}, Request state: {request_state}")
    if not state or state != request_state:
        print("State mismatch error. Aborting.")
        abort(401, description="State mismatch. Possible CSRF attack.") # Use standard abort

    if 'error' in request.args:
         error = request.args.get('error')
         error_description = request.args.get('error_description', 'No description provided.')
         print(f"Google authorization error: {error} - {error_description}")
         flash(f'Authorization failed: {error}. Please try again.', 'danger')
         # Redirect back to where they started the auth flow from
         return redirect(session.get('oauth_intended_url', url_for('index')))

    if not os.path.exists(CLIENT_SECRET_FILE):
         print(f"CRITICAL ERROR: {CLIENT_SECRET_FILE} not found during callback.")
         return render_template('error.html', error_message=f"Server configuration error: {CLIENT_SECRET_FILE} not found. Cannot complete authentication.")

    # Recreate the flow instance with the same state.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    # Use the authorization response code from Google to fetch the OAuth 2.0 tokens.
    authorization_response = request.url
    # Allow HTTP for local development (IMPORTANT: remove/guard for production)
    if 'localhost' in flow.redirect_uri or '127.0.0.1' in flow.redirect_uri:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        print("Allowing insecure transport for local development.")

    try:
        print("Fetching token from Google...")
        flow.fetch_token(authorization_response=authorization_response)
        print("Token fetched successfully.")
    except Exception as e:
        print(f"Error fetching OAuth token: {e}", exc_info=True)
        flash(f"Failed to fetch authorization token: {e}", "danger")
        # Clear potentially bad state and temporary env var
        session.pop('state', None)
        if 'OAUTHLIB_INSECURE_TRANSPORT' in os.environ: del os.environ['OAUTHLIB_INSECURE_TRANSPORT']
        return redirect(url_for('index')) # Redirect to start

    # Clear the insecure transport flag if it was set
    if 'OAUTHLIB_INSECURE_TRANSPORT' in os.environ: del os.environ['OAUTHLIB_INSECURE_TRANSPORT']

    # Store the credentials securely in the session.
    # Convert credentials object to a dictionary for session serialization.
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials) # Use helper
    if not session['credentials']:
         print("Failed to convert credentials to dictionary.")
         flash("Error storing authentication credentials.", "danger")
         return redirect(url_for('index'))

    print("Credentials stored in session.")
    # Clear the state variable used for CSRF protection.
    session.pop('state', None)

    # Redirect user back to the originally intended page (results page).
    intended_url = session.pop('oauth_intended_url', url_for('show_results'))
    flash('Successfully authorized with Google!', 'success')
    return redirect(intended_url)


@app.route('/clear_auth') # More descriptive name than /clear
def clear_authentication():
    """Clears Google credentials from the session (effectively logs out from Google part)."""
    session.pop('credentials', None)
    session.pop('extracted_data', None) # Also clear schedule data
    flash('Google authentication cleared. Upload a new image or re-authorize.', 'info')
    return redirect(url_for('index'))

# --- Google Calendar Event Creation ---

@app.route('/create_events', methods=['POST'])
def create_google_events():
    """Creates Google Calendar events using data from form and stored credentials."""
    print("Received request to create calendar events.")
    if 'credentials' not in session:
        flash('Authentication required. Please authorize with Google first.', 'warning')
        # Send user back to results page where they can see the authorize button
        return redirect(url_for('show_results'))

    # --- Get Data from Form ---
    edited_data_json = request.form.get('edited_data')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')

    # Validate required fields
    if not edited_data_json:
        flash('No schedule data submitted from the table.', 'warning')
        return redirect(url_for('show_results'))
    if not start_date_str or not end_date_str:
        flash('Start date and end date are required.', 'warning')
        return redirect(url_for('show_results'))

    # --- Parse Submitted Data ---
    try:
        schedule_data = json.loads(edited_data_json)
        if not isinstance(schedule_data, list):
             raise ValueError("Submitted schedule data is not a valid list.")
        # Optional: Add more validation per row if needed here
        print(f"Parsed schedule data: {len(schedule_data)} items.")
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON data from form.")
        flash('Invalid schedule data format received from table.', 'danger')
        return redirect(url_for('show_results'))
    except ValueError as ve:
         print(f"Error: Invalid schedule data content: {ve}")
         flash(f'Invalid schedule data: {ve}', 'danger')
         return redirect(url_for('show_results'))
    except Exception as e:
         print(f"Unexpected error parsing submitted schedule data: {e}", exc_info=True)
         flash('Error processing submitted schedule data.', 'danger')
         return redirect(url_for('show_results'))

    # Check if data is empty after parsing
    if not schedule_data:
        flash('No schedule entries to add. Please add rows to the table.', 'warning')
        return redirect(url_for('show_results'))

    # --- Get Calendar Service ---
    credentials_dict = session['credentials']
    # Use a default timezone or get from user settings if implemented
    user_timezone = request.form.get('timezone', 'UTC')

    print("Attempting to get Google Calendar service...")
    # get_calendar_service now returns (service, refreshed_creds_obj or None)
    service, refreshed_creds = get_calendar_service(credentials_dict)

    if refreshed_creds and refreshed_creds.valid:
        # Update session credentials if they were refreshed successfully
        session['credentials'] = credentials_to_dict(refreshed_creds)
        print("Session credentials updated after token refresh.")
    elif not service:
        # Service creation failed, potentially due to token refresh failure or other API issues
        session.pop('credentials', None) # Clear bad credentials
        flash('Could not connect to Google Calendar service. Authorization might have expired. Please authorize again.', 'danger')
        return redirect(url_for('show_results')) # Redirect to show authorize button again

    # --- Perform Event Creation ---
    print(f"Creating events from {start_date_str} to {end_date_str}...")
    success_count, failure_count, error_messages = create_calendar_events(
        service,
        schedule_data,
        default_time_slots, # The hardcoded time slot mapping
        start_date_str,
        end_date_str,
        user_timezone
    )
    print(f"Event creation result: Success={success_count}, Failures={failure_count}, Errors={len(error_messages)}")

    # Clear the schedule data from session after processing attempt (success or fail)
    session.pop('extracted_data', None)
    print("Cleared schedule data from session.")

    # Render summary page
    return render_template('success.html',
                           success_count=success_count,
                           failure_count=failure_count,
                           messages=error_messages) # Pass error messages list


# --- Error Handling ---
@app.errorhandler(404)
def not_found_error(error):
    """Handles 404 Not Found errors."""
    return render_template('error.html', error_message="Page Not Found (404). Please check the URL."), 404

@app.errorhandler(500)
def internal_error(error):
    """Handles 500 Internal Server errors."""
    # Log the actual error internally for debugging
    print(f"Server Error 500: {error}", exc_info=True)
    # Provide a generic message to the user
    return render_template('error.html', error_message="Internal Server Error (500). Something went wrong on our side. Please try again later."), 500

@app.errorhandler(401)
def unauthorized_error(error):
     """Handles 401 Unauthorized errors (e.g., from abort(401))."""
     # error.description might contain details from abort()
     message = getattr(error, 'description', "Authentication or authorization issue detected.")
     return render_template('error.html', error_message=f"Unauthorized (401). {message}"), 401

@app.errorhandler(405)
def method_not_allowed(error):
    """Handles 405 Method Not Allowed errors."""
    return render_template('error.html', error_message=f"Method Not Allowed (405). The request method ({request.method}) is not supported for this URL."), 405


# --- Run the App ---
if __name__ == '__main__':
    # Set host='0.0.0.0' to make accessible on your network (use with caution)
    # Use debug=False in production environments
    print("Starting Flask development server...")
    app.run(debug=True, port=5000, host='127.0.0.1')