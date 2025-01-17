# Calendar Web App
Calendar web app specifically designed for VIT students.
# VIT Calendar App

This web application is designed specifically for VIT (Vellore Institute of Technology) students to easily manage their academic schedules by converting a faculty list image into Google Calendar events.

## Features

*   **Image to Text Conversion:** Extracts faculty names, course codes, and timings from an uploaded image of the faculty list.
*   **Google Calendar Integration:** Seamlessly adds extracted events to the user's Google Calendar.
*   **User-Friendly Interface:** Simple and intuitive design for easy navigation and use.
*   **Open Source:** This project is open-source and welcomes contributions.

## Screenshots:
![image](https://github.com/user-attachments/assets/6f49ebfa-90b9-4229-af0d-8c7fab2f53e9)

![image](https://github.com/user-attachments/assets/c0e929f5-75e8-4a3d-b250-be25cc521214)

## Technologies Used

*   **Frontend:** HTML, CSS, Tailwind CSS, JavaScript, Node JS, Tabulator
*   **Backend:** Python/Flask
*   **OCR Library:** Gemini API (Reason- Was free to use and accurate compared to local OCR and other APIs, also helps in getting a formatted response directly)
*   **Google Calendar API:** To be implemented.
*   **Deployment:** To be implemented.

## Setup and Installation

1.  **Clone the repository**
2.  **Navigate to the project directory:**
3. **Install these dependencies/Modules:**
    pip install flask pillow
    pip install -q -U google-generativeai 
5.  **Run the application:**
    Run app.py and go to localhost
## How to Use

1.  Upload a clear image of your faculty list.
2.  Review the extracted information (faculty names, course codes, timings).
3.  Connect your Google Calendar account.
4.  Confirm the events to be added to your calendar.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

1.  Fork the repository.
2.  Create a new branch.
3.  Make your changes.
4.  Commit your changes.
5.  Push to the branch.
6.  Open a pull request.

## Future Enhancements

*   Support for different faculty list formats.
*   Improved error handling and feedback.
*   Mobile app development (optional).

## License

[MIT License](LICENSE)
