The /help route returns "Not Found". Create the help page:

Create frontend/help.html with a simple user guide that matches the app's purple/blue theme
Add a route in src/api/main.py to serve the help page:
@app.get("/help", response_class=HTMLResponse)
async def help_page():
    return FileResponse("frontend/help.html")

    The help page content should include:

SECTION 1: Getting Started

How to log in
What the 3 tabs do (Learn New, Use Template, Manage)

SECTION 2: Creating a Template

Step 1: Go to Learn New tab
Step 2: Give it a name
Step 3: Upload a PDF OR paste text
Step 4: Paste how you want the output to look
Step 5: Click Learn from Example

SECTION 3: Using a Template

Step 1: Go to Use Template tab
Step 2: Select your template
Step 3: Upload PDF or paste text
Step 4: Click Extract Data
Step 5: Copy the output

SECTION 4: Managing Templates

How to rename, edit, or delete

SECTION 5: Tips

Better examples = better output
One template per document type

SECTION 6: Problems

Can't see templates? Check you're logged in
Wrong output? Edit your example

Design:

Large fonts (16px+)
Short paragraphs
Numbered steps
Emoji icons for visual cues
Match the purple/blue app theme
Include a "Back to App" button