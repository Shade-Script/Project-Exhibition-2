import os
import re
import google.generativeai as genai
from PIL import Image
import io
import base64
import time

# Move the API key configuration here, outside the function
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

def run_ocr_and_extract(image_path, max_retries=3, retry_delay=10):
    """
    Runs OCR on an image using Gemini API, extracts schedule data, and retries on timeout.

    Args:
        image_path (str): The path to the image file.
        max_retries (int): The maximum number of retry attempts.
        retry_delay (int): The delay in seconds between retries.

    Returns:
        list: A list of dictionaries containing extracted data, or None on error.
    """
    for attempt in range(max_retries):
        try:
            # Configure the generative AI model
            model = genai.GenerativeModel("gemini-2.0-flash-exp")

            # Convert the image to base64
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Create the content for the API request
            contents = {
                "parts": [
                    {
                        "text": """
                            Extract the schedule information from the attached image.
                            Please provide the extracted data in a structured format with the following fields:
                            - **course_code**: The course code (e.g., CSE1001).
                            - **course_name**: The name of the course (e.g., Computer Science).
                            - **faculty_name**: The name of the faculty member.
                            - **venue**: The venue for the class (e.g., SJT-102).
                            - **slots**: A list of slots associated with the course. Each slot should follow the format of one or more letters followed by one or more numbers (e.g., A1, TA1, B2).

                            **Important Considerations:**
                            * A single course might have multiple slots. Ensure that all slots are extracted and included in the 'slots' list.
                            * Separate multiple slots with commas or spaces if they are combined in the original text.
                            * If any of the required fields are not present in the image, please leave that field blank in the output.

                            **Example Output Format:**
                            ```
                            [
                                {
                                    "course_code": "CSE1001",
                                    "course_name": "Introduction to Programming",
                                    "faculty_name": "Dr. Smith",
                                    "venue": "AB1-305",
                                    "slots": ["A1", "TA1"]
                                },
                                {
                                    "course_code": "MAT2002",
                                    "course_name": "Calculus II",
                                    "faculty_name": "Prof. Johnson",
                                    "venue": "SJT-202",
                                    "slots": ["B2", "TB2", "C2"]
                                }
                            ]
                            ```

                            Provide only the extracted data in the specified JSON format. Do not include any additional text or explanations.
                        """
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/png",  # Adjust if necessary
                            "data": image_base64,
                        }
                    },
                ]
            }

            # Generate content
            response = model.generate_content(contents)

            # Process the response
            extracted_data = process_gemini_response(response.text)

            return extracted_data

        except genai.types.generation_types.ResponseStoppedException as e:
            if "blocked due to safety reasons" in str(e):
                print(f"Attempt {attempt + 1} failed: Response blocked due to safety reasons.")
                return None  # Or handle it according to your needs

        except Exception as e:
            if "503 The service is currently unavailable" in str(e):
                print(f"Attempt {attempt + 1} failed with a service unavailable error: {e}")
            elif "timed out" in str(e).lower():
                print(f"Attempt {attempt + 1} timed out. Retrying in {retry_delay} seconds...")
            else:
                print(f"Attempt {attempt + 1} failed with an error: {e}")

            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print(f"Max retries ({max_retries}) reached. Giving up.")
                return None

def process_gemini_response(response_text):
    """
    Processes the response from the Gemini API (same as before).
    """
    try:
        # Remove any leading/trailing characters that are not part of the JSON string
        json_string = response_text.strip().strip("```json")

        # Load the JSON string into a Python list of dictionaries
        data = eval(json_string) # You can use ast.literal_eval if you have the 'ast' module

        return data

    except Exception as e:
        print(f"Error processing Gemini response: {e}")
        print(f"Response text: {response_text}")
        return []