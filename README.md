# Django BookMyShow Clone

A simple Django-based clone of a movie booking app with user authentication, movie listings, theater selection, and seat booking.

## Features

- User registration, login, and profile management
- Movie listings with search support
- Theater and showtime selection per movie
- Seat selection and booking flow
- Email booking confirmation support

## Setup

1. Create and activate a Python virtual environment
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run database migrations:
   ```bash
   python manage.py migrate
   ```
4. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Environment Variables

Set these in your deployment environment or local `.env` file:

- `DJANGO_SECRET_KEY`
- `DEBUG` (`True` or `False`)
- `DATABASE_URL` (optional; defaults to local SQLite)
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`

## Notes

- This repository excludes local environment folders and task/implementation document files.
- Keep `README.md` as the main project readme.
