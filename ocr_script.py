import os
import re
import google.generativeai as genai
from PIL import Image
import io
import base64
import time
import json # Use json module
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY") # Use environment variable

# Configure Gemini API - Moved configuration logic here for clarity
gemini_configured = False
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        gemini_configured = True
        print("Gemini API Key configured successfully.")
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        print("OCR functionality will likely fail.")
else:
    print("Warning: GEMINI_API_KEY not found in environment variables or .env file.")
    print("OCR functionality will likely fail.")

# --- Time Slot Mapping (Keep as provided) ---
time_slots = {
    "Monday": {
        "A11": {"start": "08:30", "end": "10:00"}, "B11": {"start": "10:05", "end": "11:35"},
        "C11": {"start": "11:40", "end": "13:10"}, "A21": {"start": "13:15", "end": "14:45"},
        "A14": {"start": "14:50", "end": "16:20"}, "B21": {"start": "16:25", "end": "17:55"},
        "C21": {"start": "18:00", "end": "19:30"},
    },
    "Tuesday": {
        "D11": {"start": "08:30", "end": "10:00"}, "E11": {"start": "10:05", "end": "11:35"},
        "F11": {"start": "11:40", "end": "13:10"}, "D21": {"start": "13:15", "end": "14:45"},
        "E14": {"start": "14:50", "end": "16:20"}, "E21": {"start": "16:25", "end": "17:55"},
        "F21": {"start": "18:00", "end": "19:30"},
    },
    "Wednesday": {
        "A12": {"start": "08:30", "end": "10:00"}, "B12": {"start": "10:05", "end": "11:35"},
        "C12": {"start": "11:40", "end": "13:10"}, "A22": {"start": "13:15", "end": "14:45"},
        "B14": {"start": "14:50", "end": "16:20"}, "B22": {"start": "16:25", "end": "17:55"},
        "A24": {"start": "18:00", "end": "19:30"},
    },
    "Thursday": {
        "D12": {"start": "08:30", "end": "10:00"}, "E12": {"start": "10:05", "end": "11:35"},
        "F12": {"start": "11:40", "end": "13:10"}, "D22": {"start": "13:15", "end": "14:45"},
        "F14": {"start": "14:50", "end": "16:20"}, "E22": {"start": "16:25", "end": "17:55"},
        "F22": {"start": "18:00", "end": "19:30"},
    },
    "Friday": {
        "A13": {"start": "08:30", "end": "10:00"}, "B13": {"start": "10:05", "end": "11:35"},
        "C13": {"start": "11:40", "end": "13:10"}, "A23": {"start": "13:15", "end": "14:45"},
        "C14": {"start": "14:50", "end": "16:20"}, "B23": {"start": "16:25", "end": "17:55"},
        "B24": {"start": "18:00", "end": "19:30"},
    },
    "Saturday": {
        "D13": {"start": "08:30", "end": "10:00"}, "E13": {"start": "10:05", "end": "11:35"},
        "F13": {"start": "11:40", "end": "13:10"}, "D23": {"start": "13:15", "end": "14:45"},
        "D14": {"start": "14:50", "end": "16:20"}, "D24": {"start": "16:25", "end": "17:55"},
        "E24": {"start": "18:00", "end": "19:30"},
    }
}


# --- Updated process_gemini_response ---
def process_gemini_response(response_text):
    """
    Processes the JSON response from the Gemini API using json.loads.
    """
    if not response_text:
        print("Error: Received empty response text from Gemini.")
        return []
    try:
        # Clean the response: remove potential markdown fences and strip whitespace
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        if not cleaned_text:
             print("Error: Response text became empty after cleaning markdown fences.")
             return []

        # Use json.loads for standard JSON parsing
        data = json.loads(cleaned_text)

        # Basic validation: Check if it's a list
        if not isinstance(data, list):
            print(f"Error: Parsed JSON data is not a list. Type: {type(data)}")
            print(f"Cleaned text was: {cleaned_text}")
            return []

        # Further validation and normalization
        validated_data = []
        for item in data:
            if isinstance(item, dict):
                # Normalize keys and default values
                normalized_item = {
                    'course_code': str(item.get('course_code', "")).strip(),
                    'course_name': str(item.get('course_name', "")).strip(),
                    'faculty_name': str(item.get('faculty_name', "")).strip(),
                    'venue': str(item.get('venue', "")).strip(),
                    'slots': [] # Default to empty list
                }

                # Process slots: ensure it's a list of strings
                slots_raw = item.get('slots')
                if isinstance(slots_raw, list):
                    normalized_item['slots'] = [str(s).strip().upper() for s in slots_raw if str(s).strip()]
                elif isinstance(slots_raw, str) and slots_raw.strip():
                     # Split string by comma or space, trim, filter empty, uppercase
                     normalized_item['slots'] = [s.strip().upper() for s in re.split(r'[,\s]+', slots_raw) if s.strip()]

                validated_data.append(normalized_item)
            else:
                print(f"Warning: Skipping non-dictionary item in JSON list: {item}")

        return validated_data

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        print(f"Response text (cleaned) that failed parsing was:\n---\n{cleaned_text}\n---")
        return [] # Return empty list on JSON parsing failure
    except Exception as e: # Catch other potential errors during validation
        print(f"An unexpected error occurred during response processing: {e}")
        print(f"Response text (cleaned) was:\n---\n{cleaned_text}\n---")
        return []


# --- Updated run_ocr_and_extract ---
def run_ocr_and_extract(image_data, mime_type="image/png", max_retries=3, retry_delay=10):
    """
    Runs OCR on image data using Gemini API, requests JSON, extracts schedule data,
    and retries on timeout/errors.
    """
    global gemini_configured
    if not gemini_configured:
         print("Error: Gemini API is not configured. Cannot run OCR.")
         # Return None to indicate a configuration failure upstream
         # Or potentially raise an Exception
         return None

    # Configure the model
    # Using 'gemini-1.5-flash-latest' as it's generally available and capable
    try:
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
    except Exception as e:
        print(f"Error creating Gemini model: {e}")
        return None # Cannot proceed without a model

    # Prepare image data
    try:
        image_base64 = base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"Error encoding image to base64: {e}")
        return None # Cannot proceed without image data


    # --- JSON Prompt ---
    prompt = """
Extract the schedule information from the attached image.
Provide the extracted data strictly in **JSON format**. The output should be a JSON array (list) of JSON objects (dictionaries).

Each JSON object in the array must contain the following keys:
- "course_code": (string) The course code (e.g., "CSE1001"). Use an empty string "" if not found.
- "course_name": (string) The name of the course (e.g., "Computer Science"). Use an empty string "" if not found.
- "faculty_name": (string) The name of the faculty member. Use an empty string "" if not found.
- "venue": (string) The venue for the class (e.g., "SJT-102"). Use an empty string "" if not found.
- "slots": (JSON array of strings) A list of slot codes associated with the course (e.g., ["A11", "TA11", "B21"]). Ensure this is ALWAYS an array, even if empty or with one slot. Split combined slots (like "A11, TA11" or "B21 TB21") into separate strings within the array.

Important Rules:
* The entire output MUST be **valid JSON**, starting with `[` and ending with `]`.
* Do NOT include any text before or after the JSON array.
* Do NOT use markdown formatting (like ```json) around the JSON output.
* Use double quotes (") for all keys and string values as required by JSON.
* Use `""` (empty string) for any missing string values.
* Ensure the "slots" value is always a JSON array of strings `["slot1", "slot2", ...]`.

Example Output Format (Strict JSON):
[
    {"course_code": "CSE1001", "course_name": "Intro to Prog", "faculty_name": "Dr. Smith", "venue": "AB1-305", "slots": ["A11", "TA11"]},
    {"course_code": "MAT2002", "course_name": "Calculus II", "faculty_name": "Prof. Johnson", "venue": "SJT-202", "slots": ["B21", "TB21", "C21"]},
    {"course_code": "PHY1001", "course_name": "Physics", "faculty_name": "", "venue": "TT-404", "slots": ["F11"]},
    {"course_code": "HUM1021", "course_name": "Ethics", "faculty_name": "Dr. Davis", "venue": "", "slots": []}
]
"""

    contents = {
        "parts": [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_base64,
                }
            },
        ]
    }

    # --- Generation and Retry Logic ---
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}: Sending request to Gemini API...")
            # Add safety settings if needed
            # safety_settings = [
            #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            # ]
            # response = model.generate_content(contents, safety_settings=safety_settings)
            response = model.generate_content(contents)

            print(f"Attempt {attempt + 1}: Received response from Gemini API.")
            # print(f"Raw Gemini Response Text (Attempt {attempt + 1}):\n---\n{response.text}\n---") # Debug Raw Response

            # Process the response using the updated JSON parser
            extracted_data = process_gemini_response(response.text)
            print(f"Attempt {attempt + 1}: Processed Data: {extracted_data}")

            # Return the result (could be an empty list if parsing failed or no data found)
            return extracted_data

        # --- Specific Exception Handling ---
        except genai.types.generation_types.SafetyError as e:
            print(f"Attempt {attempt + 1} failed: Response blocked due to safety reasons: {e}")
            # Consider logging e.feedback for details
            return None  # Indicate safety block failure

        except genai.types.generation_types.StopCandidateException as e:
             print(f"Attempt {attempt + 1} failed: Generation stopped unexpectedly: {e}")
             return None # Indicate unexpected stop

        except Exception as e:
            error_message = str(e).lower()
            # Check for common transient errors or specific API errors
            if "503" in error_message or "service unavailable" in error_message:
                print(f"Attempt {attempt + 1} failed with a service unavailable error: {e}")
            elif "timed out" in error_message or "deadline exceeded" in error_message:
                print(f"Attempt {attempt + 1} timed out.")
            elif "api key not valid" in error_message:
                 print(f"Attempt {attempt + 1} failed: Invalid API Key. Check configuration.")
                 return None # Don't retry on invalid key
            elif "resource has been exhausted" in error_message or "quota exceeded" in error_message:
                 print(f"Attempt {attempt + 1} failed: Quota Exceeded. {e}")
                 return None # Don't retry on quota issues
            elif "user location is not supported" in error_message:
                 print(f"Attempt {attempt + 1} failed: User location not supported for this API. {e}")
                 return None # Don't retry region errors
            else:
                # Catch other potential API errors or unexpected issues
                print(f"Attempt {attempt + 1} failed with an unexpected error: {type(e).__name__}: {e}")

            # Retry logic
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"Max retries ({max_retries}) reached. Giving up.")
                return None # Indicate final failure after retries

    # Fallback if loop finishes unexpectedly (shouldn't happen with return inside loop)
    print("Exited retry loop unexpectedly.")
    return None