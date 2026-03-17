# SmartChat AI

SmartChat AI is a Django-based intelligent learning assistant designed for schools.
It helps students interact with an AI chatbot for academic support while giving teachers analytics and performance insights.

## Features

* AI-powered chatbot using Gemini
* Student learning dashboard
* Teacher analytics and reports
* Daily quiz system
* Chat session tracking
* School and division level performance monitoring

## Tech Stack

* **Backend:** Django (Python)
* **AI Integration:** Google Gemini API
* **Frontend:** HTML, CSS, JavaScript
* **Database:** SQLite
* **Version Control:** Git & GitHub

## Project Structure

```
app/                # Main Django application
smartbot/           # Project configuration
templates/          # Shared templates
static/             # Static assets
manage.py           # Django management script
requirements.txt    # Project dependencies
```

## Setup Instructions

1. Clone the repository

```
git clone https://github.com/racheal-22/Smartchat-.git
cd smartbot
```

2. Create virtual environment

```
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies

```
pip install -r requirements.txt
```

4. Run migrations

```
python manage.py migrate
```

5. Start the server

```
python manage.py runserver
```

Open in browser:

```
http://127.0.0.1:8000
```


