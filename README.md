# Pare Email Suite

# Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   `pip3` may be required in place of `pip`.

2. Set the required environment variables (optional defaults exist), especially `OPENAI_API_KEY` for AI classification:
   - `SECRET_KEY`
   - `FLASK_SECRET_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
   - `OPENAI_API_KEY`
   - `FRONTEND_REDIRECT_KEY`

Do so in a `.env` file.

3. Next navigate to the terminal ensure you are in the `pare-email-suite` folder.

Run the following command:
`source venv/bin/activate`

Next in a seperate terminal ensure you are in the `frontend` folder, a sub folder within the `pare-email-suite` folder.

Run the following command:
`npm run dev`

4. The application should now be available at:
http://localhost:5173/

5. Note this application is not approved by Google Cloud API (still in developer mode).

Therefore the only emails approved for its use are my own and my TF Mo's harvard college email. Additional emails can be added upon request. Reach out to Finán for specific api keys as needed for key security.

6. My video!
https://youtu.be/KmVPhRVjLzE